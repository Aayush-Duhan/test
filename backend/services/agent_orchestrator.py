"""AI Agent Orchestrator — core loop.

Implements the LLM-driven tool orchestration loop:
  1. Send context + tool schemas to Cortex LLM
  2. LLM decides: run_command / pause / finish
  3. Execute command in the user's PTY terminal, capture output
  4. On failure: LLM analyses error → retry (budget)
  5. On pause:  persist state, return guidance
  6. Loop until finish/pause/cancel

Yields SSE-style events consumable by ``build_data_stream``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from services.agent_run_store import AgentRun, RunStatus, ToolTrace
from services.cortex_chat_service import _extract_text_from_message, _stream_cortex
from services.pty_service import get_session
from services.snowflake_session_manager import SnowflakeContext
from schemas import ChatMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt for the orchestrator
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = """\
You are an AI agent that orchestrates database migration tasks by running shell commands in the user's terminal.

## Instructions
- Analyze the user's request and decide what to do next.
- You MUST respond with ONLY a single JSON object (no extra text) in one of these formats:

### To run a shell command:
```json
{{"action": "run_command", "command": "<full shell command>", "reasoning": "Why this command"}}
```

### To pause and ask for user guidance:
```json
{{"action": "pause", "guidance": "What you need from the user"}}
```

### To finish the run:
```json
{{"action": "finish", "summary": "What was accomplished"}}
```

## Rules
- ONLY output a single JSON object. No narrative text, no explanations outside JSON.
- After each command execution you will receive the terminal output.
- If a command fails, analyze the error and decide whether to retry with a different command, or pause for user input.
- Always explain your reasoning inside the JSON "reasoning" field.
- Be concise.
"""


# ---------------------------------------------------------------------------
# LLM interaction helpers
# ---------------------------------------------------------------------------

def _build_agent_messages(
    run: AgentRun,
    user_messages: list[ChatMessage],
) -> list[ChatMessage]:
    """Build the message history for the LLM, including tool traces."""
    messages: list[ChatMessage] = []

    # System prompt
    messages.append(ChatMessage(role="system", content=AGENT_SYSTEM_PROMPT))

    # User messages
    for msg in user_messages:
        messages.append(msg)

    # Replay tool traces as assistant/user message pairs
    for trace in run.tool_traces:
        # Assistant decided to run the command
        messages.append(ChatMessage(
            role="assistant",
            content=json.dumps({
                "action": "run_command",
                "command": trace.command,
            }),
        ))

        # Command result as user message
        result_text = f"Command: {trace.command}\n"

        if trace.output:
            # Truncate very long outputs
            output = trace.output if len(trace.output) <= 3000 else (
                trace.output[:1500] + "\n...(truncated)...\n" + trace.output[-500:]
            )
            result_text += f"\nTerminal Output:\n{output}"

        if trace.error:
            result_text += f"\nError: {trace.error}"

        messages.append(ChatMessage(role="user", content=result_text))

    return messages


def _parse_llm_decision(text: str) -> dict[str, Any]:
    """Extract the JSON decision from LLM response text.

    The LLM may wrap the JSON in markdown code blocks; we handle that.
    """
    cleaned = text.strip()

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
        cleaned = "\n".join(json_lines)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                pass

    return {"action": "pause", "guidance": f"Could not parse LLM response as JSON: {text[:200]}"}


def _call_cortex_sync(
    context: SnowflakeContext,
    messages: list[ChatMessage],
) -> str:
    """Call Cortex LLM synchronously and return the full response text."""
    chunks: list[str] = []

    for event_kind, value in _stream_cortex(context, messages):
        if event_kind == "delta":
            chunks.append(value)

    return "".join(chunks)


# ---------------------------------------------------------------------------
# Main orchestration loop
# ---------------------------------------------------------------------------

async def run_agent_orchestrator(
    context: SnowflakeContext,
    run: AgentRun,
    user_messages: list[ChatMessage],
) -> AsyncIterator[dict[str, Any]]:
    """Execute the agent orchestration loop, yielding SSE events.

    Events emitted:
        - ``{"type": "agent-thinking", "text": "..."}``
        - ``{"type": "tool-start", "command": "..."}``
        - ``{"type": "tool-end", "command": "...", "success": bool}``
        - ``{"type": "agent-decision", "decision": {...}}``
        - ``{"type": "agent-pause", "guidance": "..."}``
        - ``{"type": "agent-finish", "summary": "..."}``
        - ``{"type": "agent-error", "error": "..."}``
    """
    loop = asyncio.get_running_loop()
    max_iterations = 50  # safety limit

    for iteration in range(max_iterations):
        # Check if cancelled
        if run.abort_event.is_set() or run.status == RunStatus.CANCELLED:
            yield {"type": "agent-finish", "summary": "Run was cancelled."}
            return

        # Check if paused — wait for resume
        while run.status == RunStatus.PAUSED:
            await asyncio.sleep(0.5)
            if run.abort_event.is_set():
                yield {"type": "agent-finish", "summary": "Run was cancelled while paused."}
                return

        # Build messages and call LLM
        yield {"type": "agent-thinking", "text": "Deciding next action..."}

        messages = _build_agent_messages(run, user_messages)

        try:
            llm_response = await loop.run_in_executor(
                None,
                lambda: _call_cortex_sync(context, messages),
            )
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            yield {"type": "agent-error", "error": f"LLM call failed: {exc}"}
            return

        # Parse the LLM's decision
        decision = _parse_llm_decision(llm_response)
        action = decision.get("action", "pause")

        yield {"type": "agent-decision", "decision": decision, "rawResponse": llm_response}

        # ---------------------------------------------------------------
        # FINISH
        # ---------------------------------------------------------------
        if action == "finish":
            summary = decision.get("summary", "Agent run completed.")
            run.status = RunStatus.FINISHED
            yield {"type": "agent-finish", "summary": summary}
            return

        # ---------------------------------------------------------------
        # PAUSE
        # ---------------------------------------------------------------
        if action == "pause":
            guidance = decision.get("guidance", "Agent paused. Waiting for user input.")
            run.status = RunStatus.PAUSED
            run.guidance = guidance
            yield {"type": "agent-pause", "guidance": guidance}
            return

        # ---------------------------------------------------------------
        # RUN COMMAND (via PTY terminal)
        # ---------------------------------------------------------------
        if action == "run_command":
            command = decision.get("command", "")

            if not command:
                yield {"type": "agent-error", "error": "Empty command from LLM"}
                run.add_trace(ToolTrace(
                    command="",
                    error="Empty command",
                ))
                continue

            # Find the user's PTY session
            pty_session = get_session(run.session_id)

            if pty_session is None or not pty_session.is_alive:
                error_msg = "No active terminal session. Please open the terminal first."
                yield {"type": "agent-error", "error": error_msg}
                run.status = RunStatus.PAUSED
                run.guidance = error_msg
                yield {"type": "agent-pause", "guidance": error_msg}
                return

            yield {"type": "tool-start", "command": command}

            # Execute the command in the PTY
            try:
                output = await pty_session.execute_command(command)
                success = True
                error = None
            except Exception as exc:
                logger.error("PTY command execution error: %s", exc)
                output = ""
                success = False
                error = str(exc)

            # Record trace
            trace = ToolTrace(
                command=command,
                output=output,
                error=error,
                success=success,
            )
            run.add_trace(trace)

            yield {
                "type": "tool-end",
                "command": command,
                "success": success,
            }

            # -------------------------------------------------------
            # Error handling: retry logic
            # -------------------------------------------------------
            if not success:
                if run.retries_used >= run.retry_budget:
                    guidance = (
                        f"Command failed and retry budget is exhausted "
                        f"({run.retries_used}/{run.retry_budget}). "
                        f"Error: {error}"
                    )
                    run.status = RunStatus.PAUSED
                    run.guidance = guidance
                    yield {"type": "agent-pause", "guidance": guidance}
                    return

                run.retries_used += 1

            continue

        # Unknown action
        yield {"type": "agent-error", "error": f"Unknown action: {action}"}
        run.add_trace(ToolTrace(
            command="",
            error=f"Unknown action from LLM: {action}",
        ))

    # Safety limit reached
    yield {"type": "agent-finish", "summary": "Maximum iterations reached. Run stopped."}
    run.status = RunStatus.FINISHED
