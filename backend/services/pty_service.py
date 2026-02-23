"""PTY session management using pywinpty for Windows.

Provides a ``PtySession`` class that spawns a real shell process
(PowerShell by default) via the Windows ConPTY API and exposes
async-friendly read/write/resize/close methods.

Uses a tap/callback pattern for command capture: the WebSocket
handler is the SINGLE reader (``read()``). When the agent runs a
command via ``execute_command()``, it installs a capture tap so
the existing reader also copies data into a buffer.

Command completion is detected by appending a unique marker echo
to the command (``; echo __MARKER__``). When the marker appears in
the captured output, we know the command has finished — no fragile
idle-timeout guessing required.

Includes a global session registry so the agent orchestrator can
write commands into a user's existing terminal session.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import time
from threading import Lock

from winpty import PtyProcess  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Resolve shell — prefer PowerShell, fall back to cmd.exe
_POWERSHELL = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
_DEFAULT_SHELL = _POWERSHELL

# Regex to strip ANSI escape sequences for reliable marker detection
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b\[[\?]?[0-9;]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return _ANSI_RE.sub("", text)


class PtySession:
    """Wraps a single PTY process with async helpers.

    The WebSocket handler calls ``read()`` in a loop — it is the sole
    reader of the PTY output.  When ``execute_command()`` is active it
    installs a *tap*: every chunk that ``read()`` returns is also
    appended to a capture buffer and an ``asyncio.Event`` is set so
    that ``execute_command()`` can detect new data without polling.
    """

    def __init__(self, cols: int = 80, rows: int = 24, shell: str | None = None):
        self._cols = cols
        self._rows = rows
        self._shell = shell or _DEFAULT_SHELL
        self._process: PtyProcess | None = None
        self._closed = False

        # Tap / capture state (set by execute_command, read by read)
        self._capturing = False
        self._capture_buffer: list[str] = []
        self._capture_event: asyncio.Event = asyncio.Event()
        self._current_marker: str | None = None  # set during execute_command

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def spawn(self) -> None:
        """Spawn the shell process inside a PTY."""
        logger.info("Spawning PTY: shell=%s cols=%d rows=%d", self._shell, self._cols, self._rows)
        self._process = PtyProcess.spawn(
            self._shell,
            dimensions=(self._rows, self._cols),
        )

    @property
    def is_alive(self) -> bool:
        if self._process is None or self._closed:
            return False
        return self._process.isalive()

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    async def read(self, length: int = 4096) -> str:
        """Non-blocking read from the PTY.

        Runs the blocking ``read()`` in a thread so the event loop
        stays responsive.  If a capture tap is active, the raw data
        is appended to the capture buffer, and the marker / echo
        command are stripped from the returned data so the browser
        terminal never sees them.
        """
        if self._process is None:
            raise RuntimeError("PTY not spawned")

        loop = asyncio.get_running_loop()
        try:
            data: str = await loop.run_in_executor(None, self._process.read, length)

            # Tap: copy RAW data to capture buffer (marker included)
            if data and self._capturing:
                self._capture_buffer.append(data)
                self._capture_event.set()

            # Strip marker artifacts from data sent to the browser
            if data and self._current_marker:
                data = data.replace(f" ; echo {self._current_marker}", "")
                data = data.replace(self._current_marker, "")

            return data
        except EOFError:
            return ""

    def write(self, data: str) -> None:
        """Write data (keystrokes) to the PTY stdin."""
        if self._process is None:
            raise RuntimeError("PTY not spawned")
        self._process.write(data)

    # ------------------------------------------------------------------
    # Resize
    # ------------------------------------------------------------------

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY to new dimensions."""
        if self._process is None or self._closed:
            return
        self._cols = cols
        self._rows = rows
        try:
            self._process.setwinsize(rows, cols)
        except Exception:
            logger.debug("Failed to resize PTY", exc_info=True)

    # ------------------------------------------------------------------
    # Agent command execution
    # ------------------------------------------------------------------

    async def execute_command(
        self,
        command: str,
        timeout: float = 1800.0,
    ) -> str:
        """Write a command into the PTY and capture its output.

        Appends a unique marker echo (``; echo __MARKER__``) to the
        command.  The WebSocket reader continues reading as usual; the
        tap copies every chunk into the capture buffer.  We wait until
        the marker string appears in the buffer — that means the command
        (and the echo) have both completed.

        Falls back to a 30-second idle timeout if the marker is never
        seen (e.g. if the command crashes the shell).

        Returns the captured output text (ANSI codes stripped).
        """
        if self._process is None:
            raise RuntimeError("PTY not spawned")

        # Generate a unique marker
        marker = f"__AGENT_DONE_{id(self)}_{int(time.monotonic() * 1000) % 999999}__"
        full_command = f"{command} ; echo {marker}"

        logger.info("[execute_command] START command=%r", command[:120])
        logger.info("[execute_command] marker=%s", marker)

        # Activate capture tap and set marker for filtering
        self._current_marker = marker
        self._capture_buffer.clear()
        self._capture_event.clear()
        self._capturing = True

        try:
            # Small delay to let the prompt settle
            await asyncio.sleep(0.3)

            # Write the command + marker echo
            self.write(full_command + "\r")
            logger.info("[execute_command] Wrote command to PTY")

            # Wait for the marker to appear in captured output
            start = time.monotonic()
            idle_fallback = 30.0
            last_data_time = time.monotonic()
            last_seen_len = 0

            while True:
                elapsed = time.monotonic() - start
                if elapsed >= timeout:
                    logger.warning("[execute_command] TIMEOUT after %.1fs", timeout)
                    break

                # Check for marker in captured output
                captured_raw = "".join(self._capture_buffer)
                captured_clean = _strip_ansi(captured_raw)

                if marker in captured_clean:
                    logger.info(
                        "[execute_command] MARKER FOUND after %.1fs, captured %d chars",
                        elapsed, len(captured_clean),
                    )
                    # Extract the output between command echo and marker
                    marker_idx = captured_clean.index(marker)
                    output = captured_clean[:marker_idx]

                    # Remove the first line (command echo) if present
                    first_nl = output.find("\n")
                    if first_nl >= 0:
                        output = output[first_nl + 1:]

                    return output.strip()

                # Track idle for fallback
                current_len = len(self._capture_buffer)
                if current_len > last_seen_len:
                    last_data_time = time.monotonic()
                    last_seen_len = current_len
                    logger.debug(
                        "[execute_command] New data, buffer chunks=%d, total_clean_len=%d",
                        current_len, len(captured_clean),
                    )

                idle = time.monotonic() - last_data_time
                if idle >= idle_fallback and current_len > 0:
                    logger.warning(
                        "[execute_command] IDLE FALLBACK after %.1fs idle (marker not found), "
                        "captured %d chars",
                        idle, len(captured_clean),
                    )
                    # Return what we have (stripped, without marker parsing)
                    # Remove the first line (command echo)
                    first_nl = captured_clean.find("\n")
                    if first_nl >= 0:
                        captured_clean = captured_clean[first_nl + 1:]
                    return captured_clean.strip()

                # Wait for the reader to signal new data
                self._capture_event.clear()
                try:
                    await asyncio.wait_for(self._capture_event.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    # Log periodic status (every ~10s)
                    if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                        logger.info(
                            "[execute_command] Waiting... elapsed=%.0fs, buffer_chunks=%d, "
                            "capturing=%s, is_alive=%s",
                            elapsed, len(self._capture_buffer),
                            self._capturing, self.is_alive,
                        )
                    continue

            # Timeout reached — return whatever we captured
            captured_clean = _strip_ansi("".join(self._capture_buffer))
            logger.warning(
                "[execute_command] Returning after timeout with %d chars",
                len(captured_clean),
            )
            return captured_clean.strip()

        finally:
            self._capturing = False
            buf_len = len(self._capture_buffer)
            self._capture_buffer.clear()
            self._capture_event.clear()
            logger.info("[execute_command] END, buffer had %d chunks", buf_len)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Kill the PTY process and mark as closed."""
        if self._closed:
            return
        self._closed = True

        if self._process is not None:
            try:
                if self._process.isalive():
                    self._process.terminate()
            except Exception:
                logger.debug("Error terminating PTY", exc_info=True)


# ---------------------------------------------------------------------------
# Global PTY Session Registry
# ---------------------------------------------------------------------------

_registry: dict[str, PtySession] = {}
_registry_lock = Lock()


def register_session(session_id: str, session: PtySession) -> None:
    """Register a PTY session for a given session/user ID."""
    with _registry_lock:
        _registry[session_id] = session
    logger.info("[PTY Registry] REGISTERED session_id=%s (total=%d)", session_id, len(_registry))


def unregister_session(session_id: str) -> None:
    """Remove a PTY session from the registry."""
    with _registry_lock:
        _registry.pop(session_id, None)
    logger.info("[PTY Registry] UNREGISTERED session_id=%s (total=%d)", session_id, len(_registry))


def get_session(session_id: str) -> PtySession | None:
    """Look up a registered PTY session."""
    with _registry_lock:
        found = _registry.get(session_id)
    logger.info(
        "[PTY Registry] LOOKUP session_id=%s → %s (registry keys=%s)",
        session_id,
        "FOUND" if found else "NOT FOUND",
        list(_registry.keys()),
    )
    return found
