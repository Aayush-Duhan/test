"""AI Agent Orchestrator — core loop.

Implements the LLM-driven tool orchestration loop:
  1. Send context + tool schemas to Cortex LLM
  2. LLM decides: run_tool / pause / finish
  3. Execute tool via tool_executor, stream output
  4. On failure: LLM analyses error → auto-fix if allowlisted → retry (budget)
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
from services.snowflake_session_manager import SnowflakeContext
from services.tool_definitions import get_tool, get_tools_for_llm
from services.tool_executor import OutputCallback, ToolResult, execute_tool
from schemas import ChatMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt for the orchestrator
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = """\
You are an AI agent that orchestrates database migration tasks using CLI tools.

## Available Tools
{tools_json}

## Instructions
- Analyze the user's request and decide which tool to run next.
- You MUST respond with a JSON object in one of these formats:

### To run a tool:
```json
{{"action": "run_tool", "tool": "<tool_name>", "args": {{...}}, "reasoning": "Why this tool"}}
```

### To pause and ask for user guidance:
```json
{{"action": "pause", "guidance": "What you need from the user"}}
```

### To finish the run:
```json
{{"action": "finish", "summary": "What was accomplished"}}
```

## Context
- After each tool execution, you will receive the tool's output (stdout, stderr, exit code).
- If a tool fails, analyze the error and decide whether to retry with different arguments, use a different tool, or pause for user input.
- Always explain your reasoning.
- Follow the migration sequence defined by the user.
- Be concise in your responses.
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

    # System prompt with tool schemas
    tools_json = json.dumps(get_tools_for_llm(), indent=2)
    system_prompt = AGENT_SYSTEM_PROMPT.format(tools_json=tools_json)
    messages.append(ChatMessage(role="system", content=system_prompt))

    # User messages
    for msg in user_messages:
        messages.append(msg)

    # Replay tool traces as assistant/user message pairs
    for trace in run.tool_traces:
        # Assistant decided to run the tool
        messages.append(ChatMessage(
            role="assistant",
            content=json.dumps({
                "action": "run_tool",
                "tool": trace.tool_name,
                "args": trace.args,
            }),
        ))

        # Tool result as user message
        result_text = f"Tool: {trace.tool_name}\nCommand: {trace.command}\nExit Code: {trace.exit_code}\n"

        if trace.stdout:
            # Truncate very long outputs
            stdout = trace.stdout if len(trace.stdout) <= 2000 else trace.stdout[:1000] + "\n...(truncated)...\n" + trace.stdout[-500:]
            result_text += f"\nStdout:\n{stdout}"

        if trace.stderr:
            stderr = trace.stderr if len(trace.stderr) <= 1000 else trace.stderr[:500] + "\n...(truncated)...\n" + trace.stderr[-250:]
            result_text += f"\nStderr:\n{stderr}"

        if trace.error:
            result_text += f"\nError: {trace.error}"

        messages.append(ChatMessage(role="user", content=result_text))

    return messages


def _parse_llm_decision(text: str) -> dict[str, Any]:
    """Extract the JSON decision from LLM response text.

    The LLM may wrap the JSON in markdown code blocks; we handle that.
    """
    # Strip markdown code fences if present
    cleaned = text.strip()

    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json) and last line (```)
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
# WebSocket broadcasting
# ---------------------------------------------------------------------------

async def _broadcast_to_ws(run: AgentRun, stream_name: str, data: str) -> None:
    """Send terminal output to all WebSocket subscribers of this run."""
    dead: list[Any] = []

    for ws in run.ws_connections:
        try:
            await ws.send_json({"stream": stream_name, "data": data})
        except Exception:
            dead.append(ws)

    for ws in dead:
        try:
            run.ws_connections.remove(ws)
        except ValueError:
            pass


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
        - ``{"type": "tool-start", "tool": "...", "args": {...}}``
        - ``{"type": "tool-output", "stream": "...", "data": "..."}``
        - ``{"type": "tool-end", "tool": "...", "exitCode": ..., "success": bool}``
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
        # RUN TOOL
        # ---------------------------------------------------------------
        if action == "run_tool":
            tool_name = decision.get("tool", "")
            tool_args = decision.get("args", {})

            tool = get_tool(tool_name)
            if tool is None:
                yield {"type": "agent-error", "error": f"Unknown tool: {tool_name}"}
                # Add a fake trace so the LLM knows
                run.add_trace(ToolTrace(
                    tool_name=tool_name,
                    args=tool_args,
                    command="",
                    error=f"Unknown tool: {tool_name}",
                ))
                continue

            yield {"type": "tool-start", "tool": tool_name, "args": tool_args}

            # Build the output callback that streams to both SSE and WebSocket
            sse_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            async def on_output(stream_name: str, line: str) -> None:
                event = {"type": "tool-output", "stream": stream_name, "data": line}
                await sse_queue.put(event)
                await _broadcast_to_ws(run, stream_name, line)

            # Run the tool in a task so we can yield SSE events as they arrive
            try:
                command = tool.build_command(tool_args)
            except KeyError as exc:
                yield {"type": "agent-error", "error": f"Missing argument for {tool_name}: {exc}"}
                run.add_trace(ToolTrace(
                    tool_name=tool_name,
                    args=tool_args,
                    command="",
                    error=f"Missing argument: {exc}",
                ))
                continue

            exec_task = asyncio.create_task(
                execute_tool(tool, tool_args, on_output=on_output, abort_event=run.abort_event)
            )

            # Drain the SSE queue while the tool runs
            while not exec_task.done():
                try:
                    event = await asyncio.wait_for(sse_queue.get(), timeout=0.1)
                    yield event
                except asyncio.TimeoutError:
                    continue

            # Drain remaining events
            while not sse_queue.empty():
                yield await sse_queue.get()

            result: ToolResult = exec_task.result()

            # Record trace
            trace = ToolTrace(
                tool_name=tool_name,
                args=tool_args,
                command=command,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=result.duration_seconds,
                error=result.error,
                success=result.exit_code == 0 and not result.timed_out and not result.aborted,
            )
            run.add_trace(trace)

            yield {
                "type": "tool-end",
                "tool": tool_name,
                "exitCode": result.exit_code,
                "success": trace.success,
                "duration": result.duration_seconds,
            }

            # -------------------------------------------------------
            # Error handling: retry logic
            # -------------------------------------------------------
            if not trace.success:
                if run.retries_used >= run.retry_budget:
                    guidance = (
                        f"Tool '{tool_name}' failed and retry budget is exhausted "
                        f"({run.retries_used}/{run.retry_budget}). "
                        f"Error: {result.error or result.stderr[:200]}"
                    )
                    run.status = RunStatus.PAUSED
                    run.guidance = guidance
                    yield {"type": "agent-pause", "guidance": guidance}
                    return

                # The LLM will see the failure in the next iteration
                # and can decide to retry or pause.
                run.retries_used += 1

            continue

        # Unknown action
        yield {"type": "agent-error", "error": f"Unknown action: {action}"}
        run.add_trace(ToolTrace(
            tool_name="unknown",
            args={},
            command="",
            error=f"Unknown action from LLM: {action}",
        ))

    # Safety limit reached
    yield {"type": "agent-finish", "summary": "Maximum iterations reached. Run stopped."}
    run.status = RunStatus.FINISHED
