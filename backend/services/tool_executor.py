"""Subprocess-based tool executor with real-time output streaming.

Uses ``subprocess.Popen`` with reader threads instead of ``asyncio``
subprocess APIs.  This avoids the ``NotImplementedError`` that
``asyncio.create_subprocess_shell`` raises on Windows when the event
loop is a ``SelectorEventLoop`` (the default under uvicorn).

Output is forwarded to an async callback via an ``asyncio.Queue``,
keeping the public API fully async-compatible.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from services.tool_definitions import ToolDefinition

logger = logging.getLogger(__name__)

# Type alias for the output callback: (stream_name, line_text) -> None
OutputCallback = Callable[[str, str], Awaitable[None]]


@dataclass
class ToolResult:
    """Result of a single tool execution."""

    tool_name: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    aborted: bool = False
    error: str | None = None


def _read_pipe(
    pipe,
    stream_name: str,
    lines: list[str],
    queue: asyncio.Queue | None,
    loop: asyncio.AbstractEventLoop | None,
) -> None:
    """Read a pipe line-by-line in a thread, forwarding to an async queue."""
    try:
        for raw_line in iter(pipe.readline, b""):
            line = raw_line.decode("utf-8", errors="replace")
            lines.append(line)

            if queue is not None and loop is not None:
                loop.call_soon_threadsafe(queue.put_nowait, (stream_name, line))
    except ValueError:
        # Pipe was closed
        pass
    finally:
        pipe.close()


async def execute_tool(
    tool: ToolDefinition,
    args: dict[str, Any],
    on_output: OutputCallback | None = None,
    abort_event: asyncio.Event | None = None,
) -> ToolResult:
    """Execute a tool's CLI command as a subprocess.

    Uses ``subprocess.Popen`` with reader threads so it works on every
    platform and with any asyncio event-loop implementation.

    Args:
        tool: The tool definition to execute.
        args: Arguments to fill into the command template.
        on_output: Async callback ``(stream_name, line)`` invoked for every
            line of stdout/stderr.
        abort_event: If set, the process will be killed when this event fires.

    Returns:
        A ``ToolResult`` with captured output and metadata.
    """
    start = time.monotonic()

    try:
        command = tool.build_command(args)
    except KeyError as exc:
        return ToolResult(
            tool_name=tool.name,
            exit_code=None,
            stdout="",
            stderr="",
            duration_seconds=0.0,
            error=f"Missing required argument: {exc}",
        )

    logger.info("Executing tool %s: %s", tool.name, command)

    # Start the process using Popen (works on all event loops)
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=tool.working_directory,
        )
    except OSError as exc:
        duration = time.monotonic() - start
        return ToolResult(
            tool_name=tool.name,
            exit_code=None,
            stdout="",
            stderr="",
            duration_seconds=duration,
            error=f"Failed to start process: {exc}",
        )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    # Set up async queue for forwarding output lines
    loop = asyncio.get_running_loop()
    output_queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

    # Reader threads for stdout and stderr
    stdout_thread = threading.Thread(
        target=_read_pipe,
        args=(process.stdout, "stdout", stdout_lines, output_queue, loop),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_pipe,
        args=(process.stderr, "stderr", stderr_lines, output_queue, loop),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    aborted = False

    # Watcher thread: waits for the process to finish, then signals via sentinel
    def _wait_for_process() -> None:
        process.wait()
        # Wait for reader threads to finish draining
        stdout_thread.join()
        stderr_thread.join()
        # Signal completion
        loop.call_soon_threadsafe(output_queue.put_nowait, None)

    wait_thread = threading.Thread(target=_wait_for_process, daemon=True)
    wait_thread.start()

    # Optional abort watcher
    async def _watch_abort() -> None:
        if abort_event is None:
            return
        while not abort_event.is_set():
            await asyncio.sleep(0.2)
        # Abort requested — kill the process
        try:
            process.kill()
        except OSError:
            pass

    abort_task = asyncio.create_task(_watch_abort()) if abort_event else None

    # Drain the output queue, forwarding to the callback
    deadline = time.monotonic() + tool.timeout_seconds

    try:
        while True:
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                timed_out = True
                try:
                    process.kill()
                except OSError:
                    pass
                break

            try:
                item = await asyncio.wait_for(output_queue.get(), timeout=min(remaining, 0.5))
            except asyncio.TimeoutError:
                # Check if abort was requested
                if abort_event and abort_event.is_set():
                    aborted = True
                    break
                continue

            if item is None:
                # Process finished and pipes drained
                break

            stream_name, line = item

            if on_output:
                try:
                    await on_output(stream_name, line)
                except Exception:
                    logger.debug("Output callback error for %s", stream_name, exc_info=True)

    finally:
        if abort_task:
            abort_task.cancel()

    # Ensure process has terminated
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()

    duration = time.monotonic() - start

    result = ToolResult(
        tool_name=tool.name,
        exit_code=process.returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
        duration_seconds=duration,
        timed_out=timed_out,
        aborted=aborted,
    )

    if timed_out:
        result.error = f"Process timed out after {tool.timeout_seconds}s"
        if on_output:
            await on_output("system", f"\n⏱ Timed out after {tool.timeout_seconds}s\n")

    if aborted:
        result.error = "Process was aborted"
        if on_output:
            await on_output("system", "\n⛔ Aborted by user\n")

    status = "✓" if result.exit_code == 0 else f"✗ (exit code {result.exit_code})"
    logger.info("Tool %s finished: %s in %.1fs", tool.name, status, duration)

    if on_output:
        await on_output("system", f"\n{'─' * 40}\nFinished: {status} ({duration:.1f}s)\n")

    return result
