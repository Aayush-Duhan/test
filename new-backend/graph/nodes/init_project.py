"""Node: Initialize SCAI project."""

from __future__ import annotations

import os
import shutil
import logging
from datetime import datetime

from graph.state import MigrationContext, MigrationState
from graph.nodes.helpers import log_event, is_error_state, run_subprocess_with_echo

logger = logging.getLogger(__name__)


def init_project_node(state: MigrationContext) -> MigrationContext:
    """
    Initialize scai project using subprocess + PTY echo.

    Creates a new scai project directory and runs 'scai init' command
    with the specified source language and project name.
    """
    if is_error_state(state):
        return state

    logger.info("Initializing project: %s", state.project_name)
    log_event(state, "info", f"Initializing project: {state.project_name}")

    try:
        project_path = os.path.join("projects", state.project_name)

        # Reset existing project directory if non-empty
        if os.path.isdir(project_path):
            entries = [
                e for e in os.listdir(project_path)
                if e not in {".DS_Store", "Thumbs.db", "desktop.ini"}
            ]
            if entries:
                warning_msg = (
                    f"Project directory already exists and is not empty. "
                    f"Resetting before init: {project_path}"
                )
                logger.warning(warning_msg)
                state.warnings.append(warning_msg)
                log_event(state, "warning", warning_msg)
                shutil.rmtree(project_path, ignore_errors=True)

        os.makedirs(project_path, exist_ok=True)

        cmd = [
            "scai", "init",
            "-l", state.source_language,
            "-n", state.project_name,
            "-s",
        ]

        result = run_subprocess_with_echo(cmd, cwd=project_path, session_id=state.session_id)

        if result.stdout:
            log_event(state, "info", "scai init output", {"stdout": result.stdout})
        if result.stderr:
            log_event(state, "warning", "scai init stderr", {"stderr": result.stderr})

        if result.returncode != 0:
            error_detail = (result.stderr or "").strip() or (result.stdout or "").strip() or f"Exit code {result.returncode}"
            error_msg = f"Failed to initialize project: {error_detail}"
            logger.error(error_msg)
            state.errors.append(error_msg)
            state.scai_project_initialized = False
            state.current_stage = MigrationState.ERROR
            log_event(state, "error", error_msg)
            return state

        state.project_path = project_path
        state.scai_project_initialized = True
        state.current_stage = MigrationState.INIT_PROJECT
        state.updated_at = datetime.now()
        logger.info("Project initialized at: %s", project_path)
        log_event(state, "info", f"Project initialized at: {project_path}")

    except Exception as e:
        error_msg = f"Exception during project initialization: {e}"
        logger.error(error_msg)
        state.errors.append(error_msg)
        state.scai_project_initialized = False
        state.current_stage = MigrationState.ERROR
        log_event(state, "error", error_msg)

    return state
