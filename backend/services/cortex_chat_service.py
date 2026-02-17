from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator, Iterator
from typing import Any

try:
    from schemas import ChatMessage
    from services.snowflake_session_manager import SnowflakeContext
except ImportError:  # pragma: no cover - package-style fallback
    from backend.schemas import ChatMessage
    from backend.services.snowflake_session_manager import SnowflakeContext

logger = logging.getLogger(__name__)


def _extract_text_from_message(message: ChatMessage) -> str:
    text_parts: list[str] = []

    if message.parts:
        for part in message.parts:
            if part.type == "text" and isinstance(part.text, str):
                text_parts.append(part.text)

    if text_parts:
        return "".join(text_parts)

    if isinstance(message.content, str):
        return message.content

    return ""


def _coerce_text(value: Any) -> str:
    if isinstance(value, str):
        return value

    if isinstance(value, list):
        pieces: list[str] = []

        for item in value:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                pieces.append(item["text"])

        return "".join(pieces)

    if isinstance(value, dict):
        if isinstance(value.get("content"), str):
            return value["content"]

        if isinstance(value.get("text"), str):
            return value["text"]

        try:
            return json.dumps(value)
        except TypeError:
            return str(value)

    return str(value) if value is not None else ""


def _chunk_text(content: str, chunk_size: int = 80) -> list[str]:
    if not content:
        return []

    return [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]


def _extract_response_text(response: Any) -> str:
    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                for key in ("message", "messages", "delta", "content", "text"):
                    if key in choice:
                        return _coerce_text(choice.get(key))

        for key in ("message", "content", "text"):
            if key in response:
                return _coerce_text(response.get(key))

    return _coerce_text(response)


def _normalize_usage(usage: Any) -> dict[str, int] | None:
    if not isinstance(usage, dict):
        return None

    prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
    completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")

    normalized: dict[str, int] = {}

    if isinstance(prompt_tokens, int):
        normalized["promptTokens"] = prompt_tokens

    if isinstance(completion_tokens, int):
        normalized["completionTokens"] = completion_tokens

    if isinstance(total_tokens, int):
        normalized["totalTokens"] = total_tokens

    return normalized or None


# ---------------------------------------------------------------------------
# SQL fallback helpers (used when REST API streaming is unavailable)
# ---------------------------------------------------------------------------

def _build_prompt(messages: list[ChatMessage]) -> str:
    system_chunks: list[str] = []
    dialog_chunks: list[str] = []

    for message in messages:
        content = _extract_text_from_message(message).strip()
        if not content:
            continue

        if message.role == "system":
            system_chunks.append(content)
            continue

        role_label = "Assistant" if message.role == "assistant" else "User"
        dialog_chunks.append(f"{role_label}: {content}")

    prompt_parts: list[str] = []

    if system_chunks:
        prompt_parts.append("System: " + "\n".join(system_chunks))

    prompt_parts.extend(dialog_chunks)
    prompt_parts.append("Assistant:")

    return "\n\n".join(prompt_parts).strip()


def _build_sql_statement(
    model: str,
    cortex_function: str,
    messages: list[ChatMessage],
    options: dict[str, Any],
) -> str:
    function_name = cortex_function or "complete"
    normalized_function = function_name.strip().lower()
    options_json = json.dumps(options)

    if normalized_function in {"complete", "ai_complete"} or normalized_function.startswith("complete$"):
        prompt = _build_prompt(messages)
        prompt = prompt.replace("$$", "$ $")
        model_literal = model.replace("'", "''")
        model_params: list[str] = []

        temperature = options.get("temperature")
        if isinstance(temperature, (int, float)):
            model_params.append(f"'temperature': {float(temperature)}")

        top_p = options.get("top_p")
        if isinstance(top_p, (int, float)):
            model_params.append(f"'top_p': {float(top_p)}")

        max_tokens = options.get("max_tokens")
        if isinstance(max_tokens, int):
            model_params.append(f"'max_tokens': {max_tokens}")

        model_params_literal = "{ " + ", ".join(model_params) + " }" if model_params else "{ }"

        return (
            "select AI_COMPLETE("
            f"model => '{model_literal}', "
            "prompt => $$" + prompt + "$$, "
            f"model_parameters => {model_params_literal}, "
            "show_details => true"
            ") as llm_response;"
        )
    else:
        message_dicts = [
            {
                "role": message.role,
                "content": _extract_text_from_message(message),
            }
            for message in messages
        ]
        payload = json.dumps(message_dicts)

    return (
        "select snowflake.cortex."
        f"{function_name}('{model}', parse_json($${payload}$$), parse_json($${options_json}$$))"
        " as llm_response;"
    )


def _run_cortex_request(context: SnowflakeContext, messages: list[ChatMessage]) -> tuple[str, dict[str, int] | None]:
    options = {
        "temperature": context.model_config.temperature,
        "top_p": context.model_config.top_p if context.model_config.top_p is not None else 1.0,
        "max_tokens": context.model_config.max_tokens if context.model_config.max_tokens is not None else 2048,
    }

    sql_stmt = _build_sql_statement(
        model=context.model_config.model,
        cortex_function=context.model_config.cortex_function,
        messages=messages,
        options=options,
    )

    rows = context.session.sql(sql_stmt).collect()
    raw = rows[0][0] if rows else None

    if raw is None:
        raise RuntimeError("Snowflake Cortex returned an empty response.")

    if isinstance(raw, str):
        try:
            response = json.loads(raw)
        except json.JSONDecodeError:
            return raw, None
    else:
        response = raw

    text = _extract_response_text(response)
    usage = _normalize_usage(response.get("usage") if isinstance(response, dict) else None)

    if not text.strip():
        raise RuntimeError("Snowflake Cortex returned an empty message.")

    return text, usage


def _stream_cortex_sql_fallback(
    context: SnowflakeContext,
    messages: list[ChatMessage],
) -> Iterator[tuple[str, Any]]:
    """Fallback: execute the full SQL query and then chunk the response."""
    response_text, usage = _run_cortex_request(context, messages)
    for chunk in _chunk_text(response_text):
        yield ("delta", chunk)
    if usage:
        yield ("usage", usage)


# ---------------------------------------------------------------------------
# REST API streaming (primary path — real token-by-token)
# ---------------------------------------------------------------------------

def _stream_cortex_rest_api(
    context: SnowflakeContext,
    messages: list[ChatMessage],
) -> Iterator[tuple[str, Any]]:
    """Stream from Cortex via the REST API (real token-by-token SSE streaming).

    Uses the connector's internal HTTP session (which has proper TLS adapters,
    proxy settings, and certificate handling) rather than standalone ``requests``
    to avoid TLS verification failures in corporate/proxy environments.
    """
    # Extract the raw SnowflakeConnection from the Snowpark session
    # (Snowpark stores it at session._conn._conn).
    server_conn = getattr(context.session, "_conn", None)
    conn = getattr(server_conn, "_conn", None) if server_conn else None
    if conn is None:
        raise RuntimeError("Cannot access Snowflake connector for REST API streaming.")

    rest = getattr(conn, "rest", None)
    if rest is None:
        raise RuntimeError("Snowflake connector has no REST handler.")

    token = getattr(rest, "token", None)
    if not token:
        raise RuntimeError("No valid auth token available for Cortex REST API streaming.")

    # Build the Cortex REST API URL from the connector's host
    host = getattr(conn, "host", None)
    if not host:
        account = context.connection_parameters.get("account", "")
        if not account:
            raise RuntimeError("Cannot determine Snowflake host for REST API streaming.")
        host = f"{account}.snowflakecomputing.com"

    url = f"https://{host}/api/v2/cortex/inference:complete"

    message_dicts = [
        {
            "role": message.role,
            "content": _extract_text_from_message(message),
        }
        for message in messages
    ]

    body: dict[str, Any] = {
        "model": context.model_config.model,
        "messages": message_dicts,
        "stream": True,
    }

    temperature = context.model_config.temperature
    if temperature is not None:
        body["temperature"] = temperature

    top_p = context.model_config.top_p
    if top_p is not None:
        body["top_p"] = top_p

    max_tokens = context.model_config.max_tokens
    if max_tokens is not None:
        body["max_tokens"] = max_tokens

    headers = {
        "Authorization": f'Snowflake Token="{token}"',
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    last_usage: dict[str, int] | None = None

    with rest.use_requests_session(url) as http_session:
        resp = http_session.post(url, json=body, headers=headers, stream=True, timeout=120)
        try:
            resp.raise_for_status()

            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data: "):
                    continue

                data_str = raw_line[6:]

                if data_str.strip() == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    logger.debug("Skipping unparseable SSE line: %s", data_str[:120])
                    continue

                choices = data.get("choices")
                if isinstance(choices, list) and choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield ("delta", content)

                raw_usage = data.get("usage")
                if isinstance(raw_usage, dict) and any(v for v in raw_usage.values() if v):
                    last_usage = _normalize_usage(raw_usage)
        finally:
            resp.close()

    if last_usage:
        yield ("usage", last_usage)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _stream_cortex(
    context: SnowflakeContext,
    messages: list[ChatMessage],
) -> Iterator[tuple[str, Any]]:
    """Stream from Cortex, preferring REST API streaming with SQL fallback."""
    normalized_fn = (context.model_config.cortex_function or "complete").strip().lower()
    can_use_rest = normalized_fn in {"complete", "ai_complete"}

    if can_use_rest:
        started = False
        try:
            for item in _stream_cortex_rest_api(context, messages):
                started = True
                yield item
            return
        except Exception as exc:
            if started:
                raise
            logger.info("REST API streaming unavailable, falling back to SQL: %s", exc)

    yield from _stream_cortex_sql_fallback(context, messages)


async def stream_chat_events(
    context: SnowflakeContext,
    messages: list[ChatMessage],
) -> AsyncIterator[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def emit(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def worker() -> None:
        try:
            with context.lock:
                for item in _stream_cortex(context, messages):
                    if not isinstance(item, (tuple, list)) or len(item) < 2:
                        logger.warning("Skipping malformed stream item: %r", item)
                        continue
                    evt_kind, value = item[0], item[1]
                    if evt_kind == "delta":
                        emit({"type": "delta", "delta": value})
                    elif evt_kind == "usage":
                        emit({"type": "usage", "usage": value})
        except Exception as exc:  # pragma: no cover - depends on external env
            emit({"type": "error", "error": str(exc)})
        finally:
            emit({"type": "done"})

    threading.Thread(target=worker, daemon=True).start()

    while True:
        event = await queue.get()
        event_type = event.get("type")

        if event_type == "done":
            break

        if event_type == "error":
            raise RuntimeError(event.get("error") or "Chat streaming failed")

        yield event
