from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator, Iterator
from typing import Any

from schemas import ChatMessage
from services.snowflake_session_manager import SnowflakeContext

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

# ─── Default system prompt for the chat interface ───────────────

from services.tool_definitions import get_tool, get_tools_for_llm
from services.tool_executor import execute_tool


def _build_chat_system_prompt() -> str:
    """Build the system prompt with current tool schemas."""
    tools_json = json.dumps(get_tools_for_llm(), indent=2)
    return f"""\
You are a **Database Migration Assistant** powered by Snowflake Cortex.

Your primary role is to help users migrate databases to Snowflake.

## Available Tools
You have access to the following CLI tools that you can execute on the local system:

{tools_json}

## How to Use Tools
When you need to run a tool, respond with ONLY a JSON object (no other text before or after):
{{"action": "run_tool", "tool": "<tool_name>", "args": {{...}}, "reasoning": "brief explanation"}}

Example:
{{"action": "run_tool", "tool": "run_command", "args": {{"command": "python --version"}}, "reasoning": "Checking Python version"}}

When you are done with all tool calls and want to reply to the user, respond with plain text only (no JSON).

## CRITICAL: Error Handling
When a tool fails (non-zero exit code or error output), you MUST:
1. Analyze the error message carefully
2. Determine the root cause
3. Fix the issue and retry with a corrected command (respond with another tool call JSON)
4. Only give up and respond with plain text if the error is unrecoverable

Do NOT stop after a single failure. Always attempt to resolve errors before reporting to the user.

## When NOT to Use Tools
For general questions, explanations, or conversation, respond with plain text as normal.
Do NOT wrap plain responses in JSON.

## Capabilities
1. **Initialize** migration projects using SnowConvert AI CLI (scai).
2. **Run shell commands** to inspect files, check tool versions, and execute scripts.
3. Help users through the full migration workflow.

Be specific, actionable, and concise.
"""


def _call_cortex_buffered(context: SnowflakeContext, messages: list[ChatMessage]) -> str:
    """Call Cortex LLM synchronously and return the full response text."""
    chunks: list[str] = []

    with context.lock:
        for item in _stream_cortex(context, messages):
            if not isinstance(item, (tuple, list)) or len(item) < 2:
                continue
            evt_kind, value = item[0], item[1]
            if evt_kind == "delta":
                chunks.append(value)

    return "".join(chunks)


def _try_parse_tool_call(text: str) -> dict[str, Any] | None:
    """Try to parse the LLM response as a tool call JSON.

    Returns the parsed dict if it's a valid tool call, None otherwise.
    """
    cleaned = text.strip()

    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```") and not in_block:
                in_block = True
                continue
            if line.strip() == "```" and in_block:
                break
            if in_block:
                json_lines.append(line)
        cleaned = "\n".join(json_lines).strip()

    # Try direct parse
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict) and obj.get("action") in ("run_tool", "finish", "pause"):
            return obj
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in mixed text
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            obj = json.loads(cleaned[start:end])
            if isinstance(obj, dict) and obj.get("action") in ("run_tool", "finish", "pause"):
                return obj
        except json.JSONDecodeError:
            pass

    return None


async def stream_chat_events(
    context: SnowflakeContext,
    messages: list[ChatMessage],
) -> AsyncIterator[dict[str, Any]]:
    """Unified chat + agent streaming function.

    Handles both plain conversation and tool execution in a single flow:
    1. Prepend system prompt with tool schemas
    2. Call LLM — if response is a tool call JSON, execute the tool
    3. Feed tool results back and let the LLM decide next steps
    4. Repeat until the LLM gives a plain text response
    5. Stream the final text response as delta events
    """
    # Prepend system prompt if none exists
    has_system = any(m.role == "system" for m in messages)

    if not has_system:
        messages = [
            ChatMessage(role="system", content=_build_chat_system_prompt()),
            *messages,
        ]

    loop = asyncio.get_running_loop()
    accumulated = list(messages)
    max_tool_iterations = 15

    for iteration in range(max_tool_iterations):
        # ── Show thinking indicator on subsequent iterations ──────
        if iteration > 0:
            yield {"type": "delta", "delta": "\n🔄 Analyzing results...\n\n"}

        # ── Call LLM (buffered) ──────────────────────────────────
        try:
            full_response = await loop.run_in_executor(
                None,
                lambda msgs=list(accumulated): _call_cortex_buffered(context, msgs),
            )
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            yield {"type": "delta", "delta": f"\n\n⚠️ LLM error: {exc}"}
            return

        # ── Check if it's a tool call ────────────────────────────
        tool_call = _try_parse_tool_call(full_response)

        if tool_call is None:
            # Plain text — stream it as a single delta and finish
            if full_response.strip():
                yield {"type": "delta", "delta": full_response}
            return

        action = tool_call.get("action")

        # ── FINISH ───────────────────────────────────────────────
        if action == "finish":
            summary = tool_call.get("summary", "Done.")
            yield {"type": "delta", "delta": summary}
            return

        # ── PAUSE ────────────────────────────────────────────────
        if action == "pause":
            guidance = tool_call.get("guidance", "I need more information to proceed.")
            yield {"type": "delta", "delta": guidance}
            return

        # ── RUN TOOL ─────────────────────────────────────────────
        if action == "run_tool":
            tool_name = tool_call.get("tool", "")
            tool_args = tool_call.get("args", {})
            reasoning = tool_call.get("reasoning", "")

            tool_def = get_tool(tool_name)

            if tool_def is None:
                # Unknown tool — inform the LLM and continue
                accumulated.append(ChatMessage(role="assistant", content=full_response))
                accumulated.append(ChatMessage(
                    role="user",
                    content=f"Error: Unknown tool '{tool_name}'. Available tools: {', '.join(t['name'] for t in get_tools_for_llm())}",
                ))
                continue

            # Build command
            try:
                command = tool_def.build_command(tool_args)
            except KeyError as exc:
                accumulated.append(ChatMessage(role="assistant", content=full_response))
                accumulated.append(ChatMessage(
                    role="user",
                    content=f"Error: Missing required argument {exc} for tool '{tool_name}'.",
                ))
                continue

            # ── Emit tool execution as formatted text deltas ─────
            if reasoning:
                yield {"type": "delta", "delta": f"🤔 {reasoning}\n\n"}

            yield {"type": "delta", "delta": f"```\n$ {command}\n"}

            # Execute the tool, streaming output as deltas
            output_queue: asyncio.Queue[str] = asyncio.Queue()

            async def on_output(stream_name: str, line: str) -> None:
                await output_queue.put(line)

            exec_task = asyncio.create_task(
                execute_tool(tool_def, tool_args, on_output=on_output)
            )

            # Drain output queue while tool runs
            while not exec_task.done():
                try:
                    line = await asyncio.wait_for(output_queue.get(), timeout=0.1)
                    yield {"type": "delta", "delta": line}
                except asyncio.TimeoutError:
                    continue

            # Drain remaining
            while not output_queue.empty():
                yield {"type": "delta", "delta": await output_queue.get()}

            result = exec_task.result()
            status = "✓" if result.exit_code == 0 else f"✗ exit code {result.exit_code}"
            yield {"type": "delta", "delta": f"```\n📋 {status} ({result.duration_seconds:.1f}s)\n\n"}

            # ── Feed result back to LLM ──────────────────────────
            accumulated.append(ChatMessage(role="assistant", content=full_response))

            result_text = f"Tool: {tool_name}\nCommand: {command}\nExit Code: {result.exit_code}\n"

            if result.stdout:
                stdout = result.stdout if len(result.stdout) <= 3000 else (
                    result.stdout[:1500] + "\n...(truncated)...\n" + result.stdout[-750:]
                )
                result_text += f"\nStdout:\n{stdout}"

            if result.stderr:
                stderr = result.stderr if len(result.stderr) <= 1500 else (
                    result.stderr[:750] + "\n...(truncated)...\n" + result.stderr[-375:]
                )
                result_text += f"\nStderr:\n{stderr}"

            if result.error:
                result_text += f"\nError: {result.error}"

            # Prompt the LLM to analyze errors
            if result.exit_code != 0:
                result_text += (
                    "\n\nThe command failed. Analyze the error, determine the fix, "
                    "and respond with a corrected tool call JSON. "
                    "If unrecoverable, respond with plain text explaining the issue."
                )

            accumulated.append(ChatMessage(role="user", content=result_text))
            continue

    # Safety limit
    yield {"type": "delta", "delta": "\n\n⚠️ Maximum tool iterations reached."}

