"""Node: Add source code files to SCAI project."""

from __future__ import annotations

import os
import shutil
import logging
from datetime import datetime

from graph.state import MigrationContext, MigrationState
from graph.nodes.helpers import (
    log_event, is_error_state, run_subprocess_with_echo, read_sql_files,
)

logger = logging.getLogger(__name__)


def add_source_code_node(state: MigrationContext) -> MigrationContext:
    """
    Add source code files to the scai project.

    Copies source files/directories, runs 'scai code add', and reads
    original SQL content into state.
    """
    if is_error_state(state):
        return state

    logger.info("Adding source code for project: %s", state.project_name)
    log_event(state, "info", f"Adding source code for project: {state.project_name}")

    try:
        source_dir = os.path.join(state.project_path, "source")
        source_dir_abs = os.path.abspath(source_dir)

        source_input = state.source_directory or (state.source_files[0] if state.source_files else "")
        if not source_input:
            error_msg = "No source directory provided for code add"
            logger.error(error_msg)
            state.errors.append(error_msg)
            state.current_stage = MigrationState.ERROR
            log_event(state, "error", error_msg)
            return state

        source_input_abs = os.path.abspath(source_input)
        if os.path.isfile(source_input_abs):
            source_input_abs = os.path.dirname(source_input_abs)

        if not os.path.isdir(source_input_abs):
            fallback_dir = source_dir_abs
            os.makedirs(fallback_dir, exist_ok=True)
            warning_msg = (
                f"Source directory does not exist: {source_input_abs}. "
                f"Using fallback directory: {fallback_dir}"
            )
            logger.warning(warning_msg)
            state.warnings.append(warning_msg)
            log_event(state, "warning", warning_msg)
            source_input_abs = fallback_dir

        # Clean scai destination to avoid FDS0002
        if os.path.isdir(source_dir_abs):
            shutil.rmtree(source_dir_abs)

        cmd = ["scai", "code", "add", "-i", source_input_abs]
        result = run_subprocess_with_echo(cmd, cwd=state.project_path, session_id=state.session_id)

        if result.stdout:
            log_event(state, "info", "scai code add output", {"stdout": result.stdout})
        if result.stderr:
            log_event(state, "warning", "scai code add stderr", {"stderr": result.stderr})

        if result.returncode != 0:
            error_detail = result.stderr or result.stdout or "Unknown error"
            error_msg = f"Failed to add source code: {error_detail}"
            logger.error(error_msg)
            state.errors.append(error_msg)
            state.scai_source_added = False
            state.current_stage = MigrationState.ERROR
            log_event(state, "error", error_msg)
            return state

        state.scai_source_added = True
        state.current_stage = MigrationState.ADD_SOURCE_CODE
        state.updated_at = datetime.now()
        logger.info("Source code added successfully")
        log_event(state, "info", "Source code added successfully")

        if not state.original_code:
            state.original_code = read_sql_files(source_dir)

    except Exception as e:
        error_msg = f"Exception during source code addition: {e}"
        logger.error(error_msg)
        state.errors.append(error_msg)
        state.scai_source_added = False
        state.current_stage = MigrationState.ERROR
        log_event(state, "error", error_msg)

    return state
