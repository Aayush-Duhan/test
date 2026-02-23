"""
Migration state definitions for the LangGraph workflow.

Port of old agentic_core state module — MigrationState enum and
MigrationContext dataclass containing all fields for the 9-node
autonomous migration pipeline.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


class MigrationState(Enum):
    """Enum representing all possible workflow stages."""
    IDLE = "idle"
    INIT_PROJECT = "init_project"
    ADD_SOURCE_CODE = "add_source_code"
    APPLY_SCHEMA_MAPPING = "apply_schema_mapping"
    CONVERT_CODE = "convert_code"
    EXECUTE_SQL = "execute_sql"
    SELF_HEAL = "self_heal"
    VALIDATE = "validate"
    HUMAN_REVIEW = "human_review"
    FINALIZE = "finalize"
    ERROR = "error"
    COMPLETED = "completed"


@dataclass
class MigrationContext:
    """
    Shared mutable state for the SCAI LangGraph workflow.

    Every node receives this context, mutates it, and returns it.
    The workflow runner passes it through the LangGraph StateGraph.
    """

    # Project identification
    project_name: str = ""
    project_path: str = ""
    source_language: str = "teradata"
    target_platform: str = "snowflake"

    # Snowflake connection parameters
    sf_account: str = ""
    sf_user: str = ""
    sf_role: str = ""
    sf_warehouse: str = ""
    sf_database: str = ""
    sf_schema: str = ""
    sf_authenticator: str = "externalbrowser"

    # Input files
    source_files: List[str] = field(default_factory=list)
    mapping_csv_path: str = ""
    source_directory: str = ""

    # Workflow tracking
    current_file: Optional[str] = None
    current_stage: MigrationState = MigrationState.IDLE

    # Code artifacts
    original_code: str = ""
    schema_mapped_code: str = ""
    converted_code: str = ""
    final_code: str = ""
    statement_type: str = "mixed"
    converted_files: List[str] = field(default_factory=list)

    # SCAI tool flags
    scai_project_initialized: bool = False
    scai_source_added: bool = False
    scai_converted: bool = False

    # Self-healing state
    self_heal_iteration: int = 0
    max_self_heal_iterations: int = 5
    self_heal_issues: List[Dict] = field(default_factory=list)
    self_heal_log: List[Dict] = field(default_factory=list)

    # Validation state
    validation_results: Dict = field(default_factory=dict)
    validation_passed: bool = False
    validation_issues: List[Dict] = field(default_factory=list)

    # Execution state
    execution_passed: bool = False
    execution_errors: List[Dict] = field(default_factory=list)
    execution_log: List[Dict] = field(default_factory=list)
    missing_objects: List[str] = field(default_factory=list)
    last_executed_file_index: int = -1

    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

    # Human review / intervention
    decision_history: List[Dict] = field(default_factory=list)
    requires_human_intervention: bool = False
    human_intervention_reason: str = ""
    requires_ddl_upload: bool = False
    ddl_upload_path: str = ""
    resume_from_stage: str = ""

    # Activity logging (wired to data_stream SSE via sink)
    activity_log: List[Dict] = field(default_factory=list)
    activity_log_sink: Optional[Callable[[Dict[str, Any]], None]] = None

    # LLM Supervisor routing
    supervisor_decision: str = ""       # e.g. "proceed", "self_heal", "human_review", "finalize", "abort"
    supervisor_reasoning: str = ""      # LLM's reasoning for the decision

    # SnowConvert report context memory
    report_context: Dict[str, Any] = field(default_factory=dict)
    ignored_report_codes: List[str] = field(default_factory=list)
    report_scan_summary: Dict[str, Any] = field(default_factory=dict)

    # Output
    output_path: str = ""
    output_files: List[str] = field(default_factory=list)
    summary_report: Dict = field(default_factory=dict)

    # Timestamps and session
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    session_id: str = ""  # PTY session ID for terminal echo
    run_id: str = ""      # Workflow run ID
