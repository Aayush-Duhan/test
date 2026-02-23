"""
Shared utilities for workflow nodes.

Provides the subprocess + PTY echo pattern, log_event helper,
and SQL file reading utilities used by all 9 nodes.
"""

from __future__ import annotations

import os
import subprocess
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from graph.state import MigrationContext

logger = logging.getLogger(__name__)


def log_event(
    state: MigrationContext,
    level: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a structured activity log entry and call the SSE sink if wired."""
    entry: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
        "stage": state.current_stage.value if state.current_stage else None,
    }
    if data:
        entry["data"] = data
    state.activity_log.append(entry)
    if callable(state.activity_log_sink):
        try:
            state.activity_log_sink(entry)
        except Exception:
            pass


def is_error_state(state: MigrationContext) -> bool:
    """Return True if the workflow is already in an error state."""
    from graph.state import MigrationState
    return state.current_stage == MigrationState.ERROR


def pty_echo(session_id: str, text: str) -> None:
    """
    Echo text to the PTY terminal so the frontend can see it.

    If no PTY session is registered (e.g. during tests), this is a no-op.
    """
    try:
        from services.pty_service import get_session
        pty = get_session(session_id)
        if pty is not None:
            pty.write(text + "\r\n")
    except Exception:
        pass


def run_subprocess_with_echo(
    cmd: List[str],
    cwd: str,
    session_id: str,
    timeout: float = 1800.0,
) -> subprocess.CompletedProcess:
    """
    Run a subprocess and echo its command + output to the PTY terminal.

    1. Writes the command line to PTY (so the user sees what's running)
    2. Runs subprocess.run with capture_output=True
    3. Writes stdout and stderr back to PTY for live visibility
    4. Returns the CompletedProcess result

    Args:
        cmd: Command list to execute
        cwd: Working directory
        session_id: PTY session ID for frontend echo
        timeout: Maximum seconds to wait

    Returns:
        subprocess.CompletedProcess with captured output
    """
    cmd_str = " ".join(cmd)
    pty_echo(session_id, f"$ {cmd_str}")

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        pty_echo(session_id, f"[TIMEOUT] Command timed out after {timeout}s: {cmd_str}")
        raise
    except Exception as e:
        pty_echo(session_id, f"[ERROR] Failed to run command: {e}")
        raise

    # Echo output back to terminal
    if result.stdout:
        for line in result.stdout.strip().splitlines():
            pty_echo(session_id, line)
    if result.stderr:
        for line in result.stderr.strip().splitlines():
            pty_echo(session_id, f"[stderr] {line}")

    return result


def read_sql_files(directory: str) -> str:
    """Read SQL-like files from a directory and return concatenated contents."""
    if not directory or not os.path.isdir(directory):
        return ""
    contents: List[str] = []
    for root, _, files in os.walk(directory):
        for filename in files:
            if filename.lower().endswith((".sql", ".ddl", ".btq", ".txt")):
                file_path = os.path.join(root, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        contents.append(f"-- FILE: {filename}\n{f.read()}\n")
                except Exception as e:
                    logger.warning("Failed to read %s: %s", file_path, e)
    return "\n".join(contents)


def list_sql_files(directory: str) -> List[str]:
    """Return sorted SQL-like file paths under a directory."""
    if not directory or not os.path.isdir(directory):
        return []
    sql_files: List[str] = []
    for root, _, files in os.walk(directory):
        for filename in files:
            if filename.lower().endswith((".sql", ".ddl", ".btq", ".txt")):
                sql_files.append(os.path.join(root, filename))
    sql_files.sort()
    return sql_files
