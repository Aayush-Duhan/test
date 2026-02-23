"""Node: Self-heal converted code using Snowflake Cortex LLM."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from graph.state import MigrationContext, MigrationState
from graph.nodes.helpers import log_event, is_error_state, pty_echo
from core.report_memory import build_report_context_memory, load_ignored_report_codes
from core.integrations import (
    apply_self_healing,
    format_self_heal_report,
)

logger = logging.getLogger(__name__)


def self_heal_node(state: MigrationContext) -> MigrationContext:
    """
    Attempt to fix issues found during execution/validation.

    Uses Snowflake Cortex LLM to repair code, tracking iterations
    and persisting fixes to converted files on disk.
    """
    if is_error_state(state):
        return state

    logger.info("Self-healing iteration %d for project: %s",
                state.self_heal_iteration + 1, state.project_name)
    log_event(state, "info", f"Self-healing iteration {state.self_heal_iteration + 1}")
    pty_echo(state.session_id, f"$ Self-healing iteration {state.self_heal_iteration + 1}...")

    try:
        state.self_heal_iteration += 1
        state.current_stage = MigrationState.SELF_HEAL

        # Refresh report context before each healing iteration
        report_context = build_report_context_memory(state)
        state.report_context = report_context
        state.ignored_report_codes = report_context.get("ignored_codes", load_ignored_report_codes())
        state.report_scan_summary = report_context.get("report_scan_summary", {})

        code_to_heal = state.converted_code
        if not code_to_heal:
            error_msg = "No code available for self-healing"
            logger.warning(error_msg)
            state.warnings.append(error_msg)
            state.updated_at = datetime.now()
            log_event(state, "warning", error_msg)
            return state

        def log_callback(msg):
            state.warnings.append(f"[Self-Heal Iter {state.self_heal_iteration}] {msg}")
            logger.info("Self-healing: %s", msg)
            log_event(state, "info", f"Self-healing: {msg}")

        heal_result = apply_self_healing(
            code=code_to_heal,
            issues=state.validation_issues,
            state=state,
            iteration=state.self_heal_iteration,
            statement_type=state.statement_type,
            logger_callback=log_callback,
        )

        log_callback(format_self_heal_report(heal_result))

        if heal_result.success:
            state.converted_code = heal_result.fixed_code

            # Persist healed code to converted files on disk
            if state.converted_files:
                for file_path in state.converted_files:
                    try:
                        path_obj = Path(file_path)
                        path_obj.parent.mkdir(parents=True, exist_ok=True)
                        path_obj.write_text(heal_result.fixed_code, encoding="utf-8")
                    except Exception as file_exc:
                        msg = f"Failed to persist healed code to {file_path}: {file_exc}"
                        state.warnings.append(msg)
                        log_event(state, "warning", msg)

            if heal_result.issues_fixed == 0 or state.self_heal_iteration >= state.max_self_heal_iterations:
                state.final_code = heal_result.fixed_code

            state.self_heal_log.append({
                "iteration": state.self_heal_iteration,
                "timestamp": heal_result.timestamp,
                "success": True,
                "fixes_applied": heal_result.fixes_applied,
                "issues_fixed": heal_result.issues_fixed,
                "llm_provider": "snowflake_cortex",
            })

            logger.info("Self-healing iteration %d completed successfully", state.self_heal_iteration)
            pty_echo(state.session_id, f"[OK] Self-healing iteration {state.self_heal_iteration} done")
        else:
            error_msg = heal_result.error_message or "Self-healing failed"
            state.errors.append(f"[Self-Heal Iter {state.self_heal_iteration}] {error_msg}")
            log_event(state, "error", f"Self-heal failed: {error_msg}")

            state.self_heal_log.append({
                "iteration": state.self_heal_iteration,
                "timestamp": heal_result.timestamp,
                "success": False,
                "error": heal_result.error_message,
                "llm_provider": "snowflake_cortex",
            })

            logger.warning("Self-healing iteration %d failed: %s", state.self_heal_iteration, error_msg)
            pty_echo(state.session_id, f"[WARN] Self-healing failed: {error_msg}")

        state.updated_at = datetime.now()

    except Exception as e:
        error_msg = f"Exception during self-healing: {e}"
        logger.error(error_msg)
        state.errors.append(error_msg)
        state.current_stage = MigrationState.ERROR
        log_event(state, "error", error_msg)

        state.self_heal_log.append({
            "iteration": state.self_heal_iteration,
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "error": error_msg,
        })

    return state
