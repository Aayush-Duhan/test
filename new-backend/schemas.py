"""
Pydantic schemas for API request/response payloads.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ============================================================================
# Chat
# ============================================================================

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = "claude-4-sonnet"
    cortex_function: str = "complete"
    temperature: float = 0.1
    max_tokens: int = 8192


# ============================================================================
# Snowflake Connection
# ============================================================================

class SnowflakeConnectRequest(BaseModel):
    account: str
    username: str
    role: str = ""
    warehouse: str = ""
    database: str = ""
    schema_name: str = Field("", alias="schema")
    authenticator: str = "externalbrowser"


class SnowflakeConnectResponse(BaseModel):
    session_id: str
    status: str
    database: Optional[str] = None
    schema_name: Optional[str] = None


class SnowflakeStatusResponse(BaseModel):
    connected: bool
    database: Optional[str] = None
    schema_name: Optional[str] = None
    warehouse: Optional[str] = None


# ============================================================================
# SCAI Workflow
# ============================================================================

class SCAIStartRequest(BaseModel):
    """Request to start a new SCAI migration workflow."""
    project_name: str
    source_language: str = "teradata"
    target_platform: str = "snowflake"
    source_directory: str = ""
    mapping_csv_path: str = ""
    statement_type: str = "mixed"
    max_self_heal_iterations: int = 5
    # Optional Snowflake overrides (falls back to env/config)
    sf_account: str = ""
    sf_user: str = ""
    sf_role: str = ""
    sf_warehouse: str = ""
    sf_database: str = ""
    sf_schema: str = ""
    sf_authenticator: str = ""


class SCAIStartResponse(BaseModel):
    """Response after starting a workflow."""
    run_id: str
    status: str


class SCAIStatusResponse(BaseModel):
    """Current status of a workflow run."""
    run_id: str
    status: str
    stage: str
    paused: bool = False
    requires_human_intervention: bool = False
    human_intervention_reason: str = ""
    errors: List[str] = []
    warnings_count: int = 0
    self_heal_iteration: int = 0
    summary_report: Optional[Dict[str, Any]] = None


class DDLUploadResponse(BaseModel):
    """Response after uploading DDL for human review resolution."""
    run_id: str
    status: str
    message: str


class ResumeResponse(BaseModel):
    """Response after resuming a paused workflow."""
    run_id: str
    status: str
