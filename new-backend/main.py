"""
FastAPI backend for the SCAI autonomous migration workflow.

Endpoints:
  - SCAI workflow: start, run (SSE), status, upload-ddl, resume
  - Snowflake session: connect, status, disconnect
  - File upload
  - Chat (Snowflake Cortex)
  - Terminal WebSocket (PTY)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import get_settings
from schemas import (
    ChatRequest,
    SnowflakeConnectRequest, SnowflakeConnectResponse, SnowflakeStatusResponse,
    SCAIStartRequest, SCAIStartResponse, SCAIStatusResponse,
    DDLUploadResponse, ResumeResponse,
)
from graph.state import MigrationContext
from services.workflow_runner import (
    start_workflow, get_run_status, run_workflow_stream, resume_workflow_stream,
    get_run,
)
from services.snowflake_session import SnowflakeSessionManager
from services.pty_service import PtySession, register_session, get_session
from stream.data_stream import (
    DataStreamBuilder, format_sse_data, format_sse_done,
    patch_response_headers,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title="SCAI Migration Backend", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sf_manager = SnowflakeSessionManager(
    session_ttl_days=settings.session_ttl_days,
    default_model=settings.default_cortex_model,
    default_cortex_function=settings.default_cortex_function,
)

# ============================================================================
# Upload directory
# ============================================================================
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ============================================================================
# Snowflake session endpoints
# ============================================================================

@app.post("/api/snowflake/connect", response_model=SnowflakeConnectResponse)
async def connect_snowflake(payload: SnowflakeConnectRequest):
    """Establish a Snowflake session."""
    import uuid as _uuid
    session_id = str(_uuid.uuid4())
    sf_manager.create_or_replace(session_id, payload)
    return SnowflakeConnectResponse(
        session_id=session_id,
        status="connected",
        database=payload.database or None,
        schema_name=payload.schema_name or None,
    )


@app.get("/api/snowflake/status")
async def snowflake_status(session_id: str = ""):
    """Check Snowflake connection status."""
    return sf_manager.build_status(session_id or None)


@app.post("/api/snowflake/disconnect")
async def disconnect_snowflake(session_id: str = ""):
    """Disconnect Snowflake session."""
    if session_id:
        sf_manager.disconnect(session_id)
    return {"status": "disconnected"}


# ============================================================================
# File upload
# ============================================================================

@app.post("/api/upload/{chat_id}")
async def upload_files(chat_id: str, files: list[UploadFile] = File(...)):
    """Upload source files for migration."""
    chat_upload_dir = os.path.join(UPLOAD_DIR, chat_id)
    os.makedirs(chat_upload_dir, exist_ok=True)

    uploaded = []
    for file in files:
        file_path = os.path.join(chat_upload_dir, file.filename)
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        uploaded.append({
            "name": file.filename,
            "path": file_path,
            "size": len(content),
        })

    return {"status": "ok", "files": uploaded}


# ============================================================================
# SCAI Workflow endpoints
# ============================================================================

@app.post("/api/scai/start", response_model=SCAIStartResponse)
async def start_scai_workflow(payload: SCAIStartRequest):
    """Start a new SCAI migration workflow."""
    run_id = str(uuid.uuid4())

    ctx = MigrationContext(
        project_name=payload.project_name,
        source_language=payload.source_language,
        target_platform=payload.target_platform,
        source_directory=payload.source_directory,
        mapping_csv_path=payload.mapping_csv_path,
        statement_type=payload.statement_type,
        max_self_heal_iterations=payload.max_self_heal_iterations,
        sf_account=payload.sf_account or settings.sf_account,
        sf_user=payload.sf_user or settings.sf_user,
        sf_role=payload.sf_role or settings.sf_role,
        sf_warehouse=payload.sf_warehouse or settings.sf_warehouse,
        sf_database=payload.sf_database or settings.sf_database,
        sf_schema=payload.sf_schema or settings.sf_schema,
        sf_authenticator=payload.sf_authenticator or settings.sf_authenticator,
    )

    start_workflow(run_id, ctx)

    return SCAIStartResponse(run_id=run_id, status="created")


@app.get("/api/scai/run/{run_id}")
async def run_scai_workflow(run_id: str):
    """Stream workflow execution via SSE."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_stream():
        async for event in run_workflow_stream(run_id):
            yield event
        yield format_sse_done()

    response = StreamingResponse(event_stream(), media_type="text/event-stream")
    patch_response_headers(response)
    return response


@app.get("/api/scai/status/{run_id}", response_model=SCAIStatusResponse)
async def scai_workflow_status(run_id: str):
    """Get current status of a workflow run."""
    status = get_run_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    return SCAIStatusResponse(**status)


@app.post("/api/scai/upload-ddl/{run_id}", response_model=DDLUploadResponse)
async def upload_ddl(run_id: str, file: UploadFile = File(...)):
    """Upload DDL script to resolve missing objects during human review."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    ctx: MigrationContext = run["ctx"]
    if not ctx.requires_ddl_upload:
        raise HTTPException(status_code=400, detail="Run does not require DDL upload")

    # Save DDL file
    ddl_dir = os.path.join(UPLOAD_DIR, "ddl", run_id)
    os.makedirs(ddl_dir, exist_ok=True)
    ddl_path = os.path.join(ddl_dir, file.filename)
    with open(ddl_path, "wb") as f:
        content = await file.read()
        f.write(content)

    ctx.ddl_upload_path = ddl_path
    logger.info("DDL uploaded for run %s: %s", run_id, ddl_path)

    return DDLUploadResponse(
        run_id=run_id,
        status="uploaded",
        message=f"DDL file '{file.filename}' uploaded. Call /api/scai/resume/{run_id} to continue.",
    )


@app.post("/api/scai/resume/{run_id}")
async def resume_scai_workflow(run_id: str):
    """Resume a paused workflow after human review / DDL upload."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if not run.get("paused"):
        raise HTTPException(status_code=400, detail="Run is not paused")

    async def event_stream():
        async for event in resume_workflow_stream(run_id):
            yield event
        yield format_sse_done()

    response = StreamingResponse(event_stream(), media_type="text/event-stream")
    patch_response_headers(response)
    return response


# ============================================================================
# Chat endpoint (Snowflake Cortex)
# ============================================================================

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Chat with Snowflake Cortex LLM."""
    try:
        # For chat, we'd need to resolve a session. Simplified for now:
        raise HTTPException(status_code=501, detail="Chat endpoint requires a session_id. Use /api/snowflake/connect first.")

        from langchain_community.chat_models.snowflake import ChatSnowflakeCortex
        from langchain_core.messages import HumanMessage

        chat_model = ChatSnowflakeCortex(
            model=request.model,
            cortex_function=request.cortex_function,
            session=session,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        messages_text = "\n".join(
            f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
            for m in request.messages
        )
        response = chat_model.invoke([HumanMessage(content=messages_text)])
        content = str(response.content or "").strip()

        builder = DataStreamBuilder()

        async def stream():
            text_id = builder.generate_text_id()
            yield format_sse_data(builder.create_text_delta(text_id, content))
            yield format_sse_done()

        resp = StreamingResponse(stream(), media_type="text/event-stream")
        patch_response_headers(resp)
        return resp

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Terminal WebSocket (PTY)
# ============================================================================

@app.websocket("/ws/terminal")
async def terminal_websocket(ws: WebSocket):
    """WebSocket endpoint for PTY terminal interaction."""
    await ws.accept()
    session_id = str(uuid.uuid4())

    try:
        pty = PtySession()
        pty.spawn()
        register_session(session_id, pty)
        await ws.send_json({"type": "session_id", "session_id": session_id})

        async def read_pty():
            while True:
                try:
                    data = await pty.read()
                    if data:
                        await ws.send_json({"type": "output", "data": data})
                except Exception:
                    break

        read_task = asyncio.create_task(read_pty())

        try:
            while True:
                msg = await ws.receive_json()
                if msg.get("type") == "input":
                    pty.write(msg.get("data", ""))
                elif msg.get("type") == "resize":
                    cols = msg.get("cols", 80)
                    rows = msg.get("rows", 24)
                    pty.resize(cols, rows)
        except WebSocketDisconnect:
            pass
        finally:
            read_task.cancel()

    except Exception as e:
        logger.error("Terminal WebSocket error: %s", e)
    finally:
        from services.pty_service import unregister_session
        unregister_session(session_id)
