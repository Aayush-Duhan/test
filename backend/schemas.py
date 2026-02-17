from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ClientMessagePart(BaseModel):
    type: str
    text: str | None = None
    contentType: str | None = None
    url: str | None = None
    data: Any | None = None
    toolCallId: str | None = None
    toolName: str | None = None
    state: str | None = None
    input: Any | None = None
    output: Any | None = None
    args: Any | None = None

    model_config = ConfigDict(extra="allow")


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str | None = None
    parts: list[ClientMessagePart] | None = None

    model_config = ConfigDict(extra="allow")


class ChatRequest(BaseModel):
    id: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)


class SnowflakeConnectRequest(BaseModel):
    account: str
    user: str
    role: str
    warehouse: str
    database: str
    schema_name: str = Field(alias="schema")
    authenticator: str = "externalbrowser"
    model: str | None = None
    cortex_function: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class SnowflakeModelDefaults(BaseModel):
    model: str
    cortexFunction: str


class SnowflakeConnectResponse(BaseModel):
    connected: bool
    expiresAt: datetime
    sessionId: str


class SnowflakeStatusResponse(BaseModel):
    connected: bool
    expiresAt: datetime | None = None
    sessionId: str | None = None
    modelDefaults: SnowflakeModelDefaults | None = None


class SnowflakeDisconnectResponse(BaseModel):
    disconnected: bool
