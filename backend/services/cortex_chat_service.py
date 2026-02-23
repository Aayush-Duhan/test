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

from services.pty_service import get_session


def _build_chat_system_prompt(chat_id: str, source_language: str = "", uploaded_files_dir: str = "") -> str:
    """Build the system prompt for the chat interface."""
    return f"""\
You are a Database Migration Assistant on the EY ETHAN platform.
You help users migrate databases to Snowflake using SnowConvert AI CLI (scai).

## RESPONSE FORMAT — STRICT RULES

You respond in one of two modes. Every response must be EXACTLY one mode:

**MODE A — COMMAND EXECUTION (pure JSON, nothing else)**
When you need to execute a shell command, respond with ONLY a single JSON object.
NO text before it. NO text after it. NO markdown fences. JUST the JSON.
Example:
{{"action": "run_command", "command": "python --version", "reasoning": "Checking Python version"}}

**MODE B — CONVERSATION (plain text, no JSON)**
When you want to talk to the user, respond with plain markdown text.
Do NOT include any JSON objects in a conversation response.

## CRITICAL: ONE COMMAND PER RESPONSE

- You may call **at most ONE command** per response.
- After you output a command JSON, **STOP IMMEDIATELY**. Do not write anything else.
- The command will be executed in the user's terminal and you will see the output.
- You will then see the terminal output and can decide what to do next.

## CRITICAL: NEVER HALLUCINATE RESULTS

- You have **NO ability to see command output** until the system gives it to you.
- NEVER pretend a command succeeded or failed — you do not know until you see the result.
- If you need to run 3 commands, that takes 3 separate responses.

## Common Commands
- `scai init <project_path> -l <language>` — Initialize a migration project
- `scai code add -i <input_path>` — Add source code files to a project
- `scai code convert` — Convert source code to Snowflake SQL
- Any other shell command as needed (dir, python, pip, etc.)

## Session Context

The project directory for this session is: **{chat_id}**
When creating/initializing a migration project, use "{chat_id}" as the project path.
{f'The source database language is: **{source_language}**.' if source_language else ''}
{f'The user has uploaded source files at: **{uploaded_files_dir}**.' if uploaded_files_dir else ''}

## Error Handling
When a command fails, analyze the error and respond with another command to fix and retry.
Only give up with a plain-text explanation if unrecoverable.

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
    """Try to extract the FIRST valid tool-call JSON from the LLM response.

    Handles several failure modes:
    - Pure JSON response
    - Markdown code-fenced JSON
    - Mixed narrative + JSON (extract first valid JSON object)
    - Multiple JSONs in one response (take the first one only)

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

    # Extract all top-level JSON objects using balanced-brace scanning
    def _extract_json_objects(s: str) -> list[str]:
        """Extract all balanced top-level {…} JSON objects from text."""
        objects: list[str] = []
        i = 0
        while i < len(s):
            if s[i] == "{":
                depth = 0
                start = i
                in_string = False
                escape_next = False
                while i < len(s):
                    ch = s[i]
                    if escape_next:
                        escape_next = False
                        i += 1
                        continue
                    if ch == "\\" and in_string:
                        escape_next = True
                        i += 1
                        continue
                    if ch == '"' and not escape_next:
                        in_string = not in_string
                    elif not in_string:
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                objects.append(s[start : i + 1])
                                break
                    i += 1
            i += 1
        return objects

    # Try each extracted JSON object — return the first valid tool call
    for candidate in _extract_json_objects(cleaned):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and obj.get("action") in ("run_command", "run_tool", "finish", "pause"):
                return obj
        except json.JSONDecodeError:
            continue

    return None


async def stream_chat_events(
    context: SnowflakeContext,
    messages: list[ChatMessage],
    *,
    chat_id: str = "",
    source_language: str = "",
    uploaded_files_dir: str = "",
    session_id: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """Unified chat + agent streaming function.

    Handles both plain conversation and tool execution in a single flow:
    1. Prepend system prompt
    2. Call LLM — if response is a command JSON, execute via PTY
    3. Feed terminal output back and let the LLM decide next steps
    4. Repeat until the LLM gives a plain text response
    5. Stream the final text response as delta events
    """
    # Prepend system prompt if none exists
    has_system = any(m.role == "system" for m in messages)

    if not has_system:
        messages = [
            ChatMessage(role="system", content=_build_chat_system_prompt(chat_id, source_language, uploaded_files_dir)),
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

        # If LLM mixed narrative text before the JSON, forward it to the user
        raw_stripped = full_response.strip()
        if not raw_stripped.startswith("{"):
            # Extract text before the first JSON object
            json_start = full_response.find("{")
            if json_start > 0:
                text_before = full_response[:json_start].strip()
                if text_before:
                    yield {"type": "delta", "delta": text_before + "\n\n"}
            logger.info(
                "LLM mixed narrative text with tool-call JSON (iteration %d).",
                iteration,
            )

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

        # ── RUN COMMAND (via PTY terminal) ─────────────────────
        if action in ("run_command", "run_tool"):
            # Support both new run_command and legacy run_tool format
            command = tool_call.get("command", "")
            if not command and action == "run_tool":
                # Legacy format: build command from tool args
                tool_args = tool_call.get("args", {})
                command = tool_args.get("command", "")

            reasoning = tool_call.get("reasoning", "")

            if not command:
                accumulated.append(ChatMessage(role="assistant", content=full_response))
                accumulated.append(ChatMessage(
                    role="user",
                    content="Error: Empty command. Please provide a valid shell command.",
                ))
                continue

            # ── Emit command info as formatted text deltas ─────
            if reasoning:
                yield {"type": "delta", "delta": f"🤔 {reasoning}\n\n"}

            yield {"type": "delta", "delta": f"```\n$ {command}\n"}

            # Execute via PTY terminal
            logger.info("[chat] Looking up PTY session for session_id=%r", session_id)
            pty_session = get_session(session_id) if session_id else None

            if pty_session is None or not pty_session.is_alive:
                # No terminal — tell the LLM
                logger.warning(
                    "[chat] No PTY session found! session_id=%r, pty_session=%s, is_alive=%s",
                    session_id, pty_session, pty_session.is_alive if pty_session else "N/A",
                )
                accumulated.append(ChatMessage(role="assistant", content=full_response))
                accumulated.append(ChatMessage(
                    role="user",
                    content="Error: No active terminal session. The user needs to open the terminal first.",
                ))
                yield {"type": "delta", "delta": "```\n⚠️ No active terminal. Please open the terminal panel.\n\n"}
                continue

            logger.info("[chat] PTY session found, executing command: %s", command[:120])

            try:
                output = await pty_session.execute_command(command)
                success = True
                error = None
                logger.info("[chat] Command completed. Output length=%d chars", len(output))
                if output:
                    logger.info("[chat] Output preview: %s", output[:200])
                else:
                    logger.warning("[chat] Command returned EMPTY output!")
            except Exception as exc:
                logger.error("[chat] PTY command error: %s", exc, exc_info=True)
                output = ""
                success = False
                error = str(exc)

            status = "✓" if success else f"✗ error: {error}"
            yield {"type": "delta", "delta": f"```\n📋 {status}\n\n"}

            # ── Feed result back to LLM ──────────────────────────
            accumulated.append(ChatMessage(role="assistant", content=full_response))

            result_text = f"Command: {command}\n"

            if output:
                truncated = output if len(output) <= 3000 else (
                    output[:1500] + "\n...(truncated)...\n" + output[-750:]
                )
                result_text += f"\nTerminal Output:\n{truncated}"

            if error:
                result_text += f"\nError: {error}"
                result_text += (
                    "\n\nThe command failed. Analyze the error, determine the fix, "
                    "and respond with a corrected command JSON. "
                    "If unrecoverable, respond with plain text explaining the issue."
                )

            logger.info("[chat] Feeding back to LLM: %s", result_text[:300])
            accumulated.append(ChatMessage(role="user", content=result_text))
            continue

    # Safety limit
    yield {"type": "delta", "delta": "\n\n⚠️ Maximum tool iterations reached."}

