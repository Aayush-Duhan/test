from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock


@dataclass
class StreamRecord:
    chat_id: str
    created_at: datetime


class StreamRegistry:
    """Reconnect-ready in-memory registry for chat stream handles."""

    def __init__(self) -> None:
        self._records: dict[str, StreamRecord] = {}
        self._lock = RLock()

    def register(self, chat_id: str) -> None:
        with self._lock:
            self._records[chat_id] = StreamRecord(chat_id=chat_id, created_at=datetime.now(tz=timezone.utc))

    def unregister(self, chat_id: str) -> None:
        with self._lock:
            self._records.pop(chat_id, None)

    def has_active_stream(self, chat_id: str) -> bool:
        with self._lock:
            return chat_id in self._records
