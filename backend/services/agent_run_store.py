"""In-memory store for active agent runs.

Tracks run lifecycle (running → paused → resumed → finished / cancelled)
and persists tool traces so the agent can resume from the last failure.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any


class RunStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ToolTrace:
    """Record of a single command execution within a run."""

    command: str
    output: str = ""
    error: str | None = None
    success: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class AgentRun:
    """State of a single agent orchestration run."""

    run_id: str
    session_id: str
    status: RunStatus = RunStatus.RUNNING
    tool_traces: list[ToolTrace] = field(default_factory=list)
    llm_messages: list[dict[str, Any]] = field(default_factory=list)
    retry_budget: int = 3
    retries_used: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    guidance: str | None = None  # LLM guidance shown on pause
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)

    def touch(self) -> None:
        self.updated_at = datetime.now(tz=timezone.utc)

    def add_trace(self, trace: ToolTrace) -> None:
        self.tool_traces.append(trace)
        self.touch()

    @property
    def last_trace(self) -> ToolTrace | None:
        return self.tool_traces[-1] if self.tool_traces else None

    @property
    def failed_traces(self) -> list[ToolTrace]:
        return [t for t in self.tool_traces if not t.success]


class AgentRunStore:
    """Thread-safe in-memory store for agent runs."""

    def __init__(self) -> None:
        self._runs: dict[str, AgentRun] = {}
        self._lock = RLock()

    def create_run(self, session_id: str, retry_budget: int = 3) -> AgentRun:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        run = AgentRun(
            run_id=run_id,
            session_id=session_id,
            retry_budget=retry_budget,
        )
        with self._lock:
            self._runs[run_id] = run
        return run

    def get_run(self, run_id: str) -> AgentRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def pause_run(self, run_id: str, guidance: str | None = None) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.status != RunStatus.RUNNING:
                return False
            run.status = RunStatus.PAUSED
            run.guidance = guidance
            run.touch()
            return True

    def resume_run(self, run_id: str) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.status != RunStatus.PAUSED:
                return False
            run.status = RunStatus.RUNNING
            run.guidance = None
            run.touch()
            return True

    def cancel_run(self, run_id: str) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.status in {RunStatus.FINISHED, RunStatus.CANCELLED}:
                return False
            run.status = RunStatus.CANCELLED
            run.abort_event.set()
            run.touch()
            return True

    def finish_run(self, run_id: str, status: RunStatus = RunStatus.FINISHED) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return False
            run.status = status
            run.touch()
            return True

    def list_runs(self, session_id: str | None = None) -> list[AgentRun]:
        with self._lock:
            runs = list(self._runs.values())
        if session_id:
            runs = [r for r in runs if r.session_id == session_id]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)
