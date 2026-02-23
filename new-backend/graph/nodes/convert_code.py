"""Node: Run scai code convert."""

from __future__ import annotations

import os
import logging
from datetime import datetime

from graph.state import MigrationContext, MigrationState
from graph.nodes.helpers import (
    log_event, is_error_state, run_subprocess_with_echo,
    read_sql_files, list_sql_files,
)
from core.report_memory import build_report_context_memory

logger = logging.getLogger(__name__)


def convert_code_node(state: MigrationContext) -> MigrationContext:
    """
    Run 'scai code convert' to convert source code to Snowflake.

    After conversion, reads converted files and builds report context memory
    for downstream self-healing.
    """
    if is_error_state(state):
        return state

    logger.info("Converting code for project: %s", state.project_name)
    log_event(state, "info", f"Converting code for project: {state.project_name}")

    try:
        cmd = ["scai", "code", "convert"]
        result = run_subprocess_with_echo(
            cmd, cwd=state.project_path, session_id=state.session_id,
            timeout=3600.0,  # 1 hour for large codebases
        )

        if result.stdout:
            log_event(state, "info", "scai code convert output", {"stdout": result.stdout})
        if result.stderr:
            log_event(state, "warning", "scai code convert stderr", {"stderr": result.stderr})

        if result.returncode != 0:
            error_detail = result.stderr or result.stdout or "Unknown error"
            error_msg = f"Failed to convert code: {error_detail}"
            logger.error(error_msg)
            state.errors.append(error_msg)
            state.scai_converted = False
            state.current_stage = MigrationState.ERROR
            log_event(state, "error", error_msg)
            return state

        state.scai_converted = True
        state.current_stage = MigrationState.CONVERT_CODE
        state.updated_at = datetime.now()
        logger.info("Code conversion completed successfully")
        log_event(state, "info", "Code conversion completed successfully")

        # Read converted files
        converted_dir = os.path.join(state.project_path, "converted")
        converted_files = list_sql_files(converted_dir)
        state.converted_files = converted_files
        state.converted_code = read_sql_files(converted_dir)

        if not state.converted_code:
            state.converted_code = state.schema_mapped_code or state.original_code or ""
            if state.converted_code:
                warning_msg = "Converted output files not found; using in-memory SQL content."
                state.warnings.append(warning_msg)
                log_event(state, "warning", warning_msg)

        # Build report context for self-healing
        report_context = build_report_context_memory(state)
        state.report_context = report_context
        state.ignored_report_codes = report_context.get("ignored_codes", [])
        state.report_scan_summary = report_context.get("report_scan_summary", {})

    except Exception as e:
        error_msg = f"Exception during code conversion: {e}"
        logger.error(error_msg)
        state.errors.append(error_msg)
        state.scai_converted = False
        state.current_stage = MigrationState.ERROR
        log_event(state, "error", error_msg)

    return state
