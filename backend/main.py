from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
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
from services.pty_service import PtySession, register_session, unregister_session
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

UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"

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


@app.post("/api/upload/{chat_id}")
async def upload_files(chat_id: str, files: list[UploadFile]) -> JSONResponse:
    """Accept file uploads and save them to uploads/{chat_id}/."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    upload_dir = UPLOADS_DIR / chat_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for f in files:
        if not f.filename:
            continue

        # Flatten any nested folder structure — just keep the filename
        safe_name = Path(f.filename).name
        dest = upload_dir / safe_name
        content_bytes = await f.read()
        dest.write_bytes(content_bytes)

        # Try to read as text for workbench display
        try:
            text_content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text_content = "-- binary file --"

        results.append({
            "name": safe_name,
            "path": str(dest),
            "content": text_content,
        })

    return JSONResponse(content={"files": results, "upload_dir": str(upload_dir)})


@app.post("/api/chat")
async def chat_endpoint(
    request: Request,
    payload: ChatRequest,
    protocol: str = Query("data"),
    source_language: str = Query(""),
    id: str = Query(""),
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

    chat_id = id or payload.id or f"chat-{uuid.uuid4().hex}"
    stream_registry.register(chat_id)

    # Check if user has uploaded files for this chat
    uploaded_files_dir = UPLOADS_DIR / chat_id
    has_uploads = uploaded_files_dir.exists() and any(uploaded_files_dir.iterdir())

    async def stream_response() -> AsyncIterator[str]:
        try:
            async for chunk in build_data_stream(
                request=request,
                model_events=stream_chat_events(
                    context,
                    payload.messages,
                    chat_id=chat_id,
                    source_language=source_language,
                    uploaded_files_dir=str(uploaded_files_dir) if has_uploads else "",
                    session_id=session_id,
                ),
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
# Terminal PTY WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/ws/terminal")
async def ws_terminal(websocket: WebSocket) -> None:
    """Spawn a real PTY shell and relay I/O over WebSocket."""
    await websocket.accept()

    cols = int(websocket.query_params.get("cols", 80))
    rows = int(websocket.query_params.get("rows", 24))

    # Use session cookie to register this PTY so the agent can find it
    session_id = websocket.cookies.get(settings.session_cookie_name) or "default"

    import logging as _logging
    _ws_logger = _logging.getLogger(__name__)
    _ws_logger.info(
        "[ws_terminal] cookie_name=%s session_id=%s all_cookies=%s",
        settings.session_cookie_name,
        session_id,
        dict(websocket.cookies),
    )

    session = PtySession(cols=cols, rows=rows)
    session.spawn()
    register_session(session_id, session)

    async def _pty_reader() -> None:
        """Read PTY output and forward to the WebSocket.

        This is the SINGLE reader of the PTY.  When execute_command()
        is active, the read() method also copies data into its capture
        buffer automatically (tap pattern).
        """
        try:
            while session.is_alive:
                data = await session.read(4096)
                if data:
                    await websocket.send_text(data)
                else:
                    break
        except Exception:
            pass

    reader_task = asyncio.create_task(_pty_reader())

    try:
        while True:
            raw = await websocket.receive_text()

            # Handle JSON control messages (resize)
            if raw.startswith("{"):
                try:
                    msg = json.loads(raw)
                    if msg.get("type") == "resize":
                        session.resize(msg["cols"], msg["rows"])
                        continue
                except (ValueError, KeyError):
                    pass

            # Regular keystrokes
            session.write(raw)
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        unregister_session(session_id)
        session.close()


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
