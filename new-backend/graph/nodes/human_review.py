"""Node: Pause workflow for human review."""

from __future__ import annotations

import logging
from datetime import datetime

from graph.state import MigrationContext, MigrationState
from graph.nodes.helpers import log_event, is_error_state, pty_echo

logger = logging.getLogger(__name__)


def human_review_node(state: MigrationContext) -> MigrationContext:
    """
    Pause workflow for user intervention.

    Sets state to HUMAN_REVIEW which triggers the workflow runner
    to emit a blocking event and wait for resume via API.
    """
    if is_error_state(state):
        return state

    logger.info("Requesting human review for project: %s", state.project_name)
    log_event(state, "info", "Human review requested")
    pty_echo(state.session_id, "[PAUSED] Waiting for human review...")

    try:
        state.current_stage = MigrationState.HUMAN_REVIEW
        state.requires_human_intervention = True
        state.updated_at = datetime.now()
        logger.info("Human review requested — workflow paused")

        if state.missing_objects:
            reason = f"Missing objects: {', '.join(state.missing_objects)}. Upload DDL to continue."
            if not state.human_intervention_reason:
                state.human_intervention_reason = reason
            pty_echo(state.session_id, f"  Reason: {reason}")
        elif state.human_intervention_reason:
            pty_echo(state.session_id, f"  Reason: {state.human_intervention_reason}")

    except Exception as e:
        error_msg = f"Exception during human review setup: {e}"
        logger.error(error_msg)
        state.errors.append(error_msg)
        state.current_stage = MigrationState.ERROR
        log_event(state, "error", error_msg)

    return state
