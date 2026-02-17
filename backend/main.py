from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from config import get_settings
from schemas import (
    ChatRequest,
    SnowflakeConnectRequest,
    SnowflakeConnectResponse,
    SnowflakeDisconnectResponse,
    SnowflakeStatusResponse,
)
from services.cortex_chat_service import stream_chat_events
from services.snowflake_session_manager import SnowflakeSessionError, SnowflakeSessionManager
from services.stream_registry import StreamRegistry
from stream.data_stream import build_data_stream, patch_response_headers

load_dotenv()

settings = get_settings()
session_manager = SnowflakeSessionManager(
    session_ttl_days=settings.session_ttl_days,
    default_model=settings.default_cortex_model,
    default_cortex_function=settings.default_cortex_function,
)
stream_registry = StreamRegistry()

app = FastAPI(
    title="DB Migration Agent",
    description="Backend API for the database migration agent",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "DB Migration Agent API is running"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/api/snowflake/connect", response_model=SnowflakeConnectResponse)
async def connect_snowflake(request: Request, payload: SnowflakeConnectRequest) -> JSONResponse:
    session_id = _ensure_session_id(request)

    try:
        context = await run_in_threadpool(session_manager.create_or_replace, session_id, payload)
    except SnowflakeSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response_payload = SnowflakeConnectResponse(
        connected=True,
        expiresAt=context.expires_at,
        sessionId=session_id,
    )
    response = JSONResponse(content=response_payload.model_dump(mode="json"))
    _set_session_cookie(response, session_id)

    return response


@app.get("/api/snowflake/status", response_model=SnowflakeStatusResponse)
async def snowflake_status(request: Request) -> SnowflakeStatusResponse:
    session_id = request.cookies.get(settings.session_cookie_name)
    return session_manager.build_status(session_id)


@app.post("/api/snowflake/disconnect", response_model=SnowflakeDisconnectResponse)
async def disconnect_snowflake(request: Request) -> JSONResponse:
    session_id = request.cookies.get(settings.session_cookie_name)
    disconnected = False

    if session_id:
        disconnected = await run_in_threadpool(session_manager.disconnect, session_id)

    response = JSONResponse(content=SnowflakeDisconnectResponse(disconnected=disconnected).model_dump(mode="json"))
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response


@app.post("/api/chat")
async def chat_endpoint(
    request: Request,
    payload: ChatRequest,
    protocol: str = Query("data"),
) -> StreamingResponse:
    session_id = request.cookies.get(settings.session_cookie_name)

    if not session_id:
        raise HTTPException(status_code=409, detail="Snowflake is not connected for this browser session")

    context = session_manager.get_context(session_id)

    if context is None:
        raise HTTPException(status_code=409, detail="Snowflake session expired or missing. Reconnect to continue")

    try:
        await run_in_threadpool(session_manager.validate_connection, context)
    except SnowflakeSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    session_manager.touch(context)

    chat_id = payload.id or f"chat-{uuid.uuid4().hex}"
    stream_registry.register(chat_id)

    async def stream_response() -> AsyncIterator[str]:
        try:
            async for chunk in build_data_stream(
                request=request,
                model_events=stream_chat_events(context, payload.messages),
                ping_interval_seconds=settings.sse_ping_interval_seconds,
            ):
                yield chunk
        finally:
            stream_registry.unregister(chat_id)

    response = StreamingResponse(stream_response(), media_type="text/event-stream")
    return patch_response_headers(response, protocol=protocol)


@app.get("/api/chat/{chat_id}/stream")
async def reconnect_stream(chat_id: str) -> Response:
    if stream_registry.has_active_stream(chat_id):
        return Response(status_code=204)

    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_session_id(request: Request) -> str:
    return request.cookies.get(settings.session_cookie_name) or uuid.uuid4().hex


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
