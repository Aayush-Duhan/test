from __future__ import annotations

import os
from dataclasses import dataclass


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    return default


@dataclass(frozen=True)
class Settings:
    frontend_origins: tuple[str, ...]
    session_cookie_name: str
    session_ttl_days: int
    cookie_secure: bool
    cookie_samesite: str
    sse_ping_interval_seconds: float
    default_cortex_model: str
    default_cortex_function: str


def get_settings() -> Settings:
    origins_raw = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000")
    frontend_origins = tuple(origin.strip() for origin in origins_raw.split(",") if origin.strip())

    return Settings(
        frontend_origins=frontend_origins,
        session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "snowflake_session_id"),
        session_ttl_days=int(os.getenv("SESSION_TTL_DAYS", "30")),
        cookie_secure=_parse_bool(os.getenv("COOKIE_SECURE"), default=False),
        cookie_samesite=os.getenv("COOKIE_SAMESITE", "lax"),
        sse_ping_interval_seconds=float(os.getenv("SSE_PING_INTERVAL_SECONDS", "12")),
        default_cortex_model=os.getenv("CORTEX_MODEL", "claude-4-sonnet"),
        default_cortex_function=os.getenv("CORTEX_FUNCTION", "complete"),
    )
