"""Snowflake session manager for the SCAI backend.

Manages Snowflake connections, Snowpark sessions, and Cortex model config.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock, RLock
from typing import Any

from schemas import SnowflakeConnectRequest, SnowflakeModelDefaults, SnowflakeStatusResponse


class SnowflakeSessionError(Exception):
    """Raised when a Snowflake session operation fails."""


@dataclass
class SnowflakeModelConfig:
    model: str
    cortex_function: str
    temperature: float
    top_p: float
    max_tokens: int | None


@dataclass
class SnowflakeContext:
    session_id: str
    session: Any
    model_config: SnowflakeModelConfig
    connection_parameters: dict[str, Any]
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    lock: Lock


class SnowflakeSessionManager:
    def __init__(self, session_ttl_days: int, default_model: str, default_cortex_function: str) -> None:
        self._session_ttl_days = session_ttl_days
        self._default_model = default_model
        self._default_cortex_function = default_cortex_function
        self._sessions: dict[str, SnowflakeContext] = {}
        self._lock = RLock()

    def create_or_replace(self, session_id: str, payload: SnowflakeConnectRequest) -> SnowflakeContext:
        self.disconnect(session_id)
        connection_parameters = self._build_connection_parameters(payload)

        try:
            import snowflake.connector
            from snowflake.snowpark import Session

            connector_connection = snowflake.connector.connect(**connection_parameters)
            snowpark_session = Session.builder.configs({"connection": connector_connection}).create()
        except Exception as exc:
            raise SnowflakeSessionError(f"Unable to connect to Snowflake: {exc}") from exc

        model = payload.model or self._default_model
        cortex_function = payload.cortex_function or self._default_cortex_function

        model_cfg = SnowflakeModelConfig(
            model=model,
            cortex_function=cortex_function,
            temperature=0,
            top_p=0,
            max_tokens=None,
        )

        now = datetime.now(tz=timezone.utc)
        context = SnowflakeContext(
            session_id=session_id,
            session=snowpark_session,
            model_config=model_cfg,
            connection_parameters=connection_parameters,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=self._session_ttl_days),
            lock=Lock(),
        )

        with self._lock:
            self._sessions[session_id] = context

        return context

    def get_context(self, session_id: str) -> SnowflakeContext | None:
        with self._lock:
            context = self._sessions.get(session_id)
        if context is None:
            return None
        if datetime.now(tz=timezone.utc) >= context.expires_at:
            self.disconnect(session_id)
            return None
        return context

    def touch(self, context: SnowflakeContext) -> None:
        now = datetime.now(tz=timezone.utc)
        context.last_used_at = now
        context.expires_at = now + timedelta(days=self._session_ttl_days)

    def disconnect(self, session_id: str) -> bool:
        with self._lock:
            context = self._sessions.pop(session_id, None)
        if context is None:
            return False
        try:
            context.session.close()
        except Exception:
            pass
        return True

    def validate_connection(self, context: SnowflakeContext) -> None:
        try:
            context.session.sql("SELECT 1").collect()
        except Exception as exc:
            self.disconnect(context.session_id)
            raise SnowflakeSessionError(
                "Snowflake session is no longer valid. Please reconnect."
            ) from exc

    def build_status(self, session_id: str | None) -> SnowflakeStatusResponse:
        if not session_id:
            return SnowflakeStatusResponse(connected=False)
        context = self.get_context(session_id)
        if context is None:
            return SnowflakeStatusResponse(connected=False)
        self.touch(context)
        return SnowflakeStatusResponse(
            connected=True,
            expiresAt=context.expires_at,
            sessionId=context.session_id,
            modelDefaults=SnowflakeModelDefaults(
                model=context.model_config.model,
                cortexFunction=context.model_config.cortex_function,
            ),
        )

    def _build_connection_parameters(self, payload: SnowflakeConnectRequest) -> dict[str, Any]:
        return {
            "account": payload.account,
            "user": payload.user,
            "authenticator": payload.authenticator,
            "role": payload.role,
            "warehouse": payload.warehouse,
            "database": payload.database,
            "schema": payload.schema_name,
            "client_store_temporary_credential": True,
            "client_session_keep_alive": True,
            "client_request_mfa_token": True,
        }
