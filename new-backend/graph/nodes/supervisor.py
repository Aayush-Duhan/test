"""
Node: LLM Supervisor — the agentic brain of the workflow.

Runs after every task node. Calls Snowflake Cortex to evaluate
the current migration state and decide the next action.
Streams reasoning to the frontend via activity_log_sink.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from graph.state import MigrationContext, MigrationState
from graph.nodes.helpers import log_event, pty_echo

logger = logging.getLogger(__name__)

# Maps current_stage → natural "proceed" target
_NATURAL_NEXT: dict[str, str] = {
    MigrationState.INIT_PROJECT.value: "add_source_code",
    MigrationState.ADD_SOURCE_CODE.value: "apply_schema_mapping",
    MigrationState.APPLY_SCHEMA_MAPPING.value: "convert_code",
    MigrationState.CONVERT_CODE.value: "execute_sql",
    MigrationState.EXECUTE_SQL.value: "validate",
    MigrationState.SELF_HEAL.value: "validate",
    MigrationState.VALIDATE.value: "finalize",
    MigrationState.HUMAN_REVIEW.value: "execute_sql",
    MigrationState.FINALIZE.value: "__end__",
}

# Maps current_stage → allowed LLM decisions
_ALLOWED_DECISIONS: dict[str, list[str]] = {
    MigrationState.INIT_PROJECT.value: ["proceed", "abort"],
    MigrationState.ADD_SOURCE_CODE.value: ["proceed", "abort"],
    MigrationState.APPLY_SCHEMA_MAPPING.value: ["proceed", "abort"],
    MigrationState.CONVERT_CODE.value: ["proceed", "abort"],
    MigrationState.EXECUTE_SQL.value: ["proceed", "self_heal", "human_review", "finalize", "abort"],
    MigrationState.SELF_HEAL.value: ["proceed", "self_heal", "finalize", "abort"],
    MigrationState.VALIDATE.value: ["proceed", "self_heal", "finalize", "abort"],
    MigrationState.HUMAN_REVIEW.value: ["proceed", "abort"],
    MigrationState.FINALIZE.value: ["proceed"],
}


def _build_state_summary(state: MigrationContext) -> str:
    """Build a concise state summary for the LLM prompt."""
    lines = [
        f"Project: {state.project_name}",
        f"Current stage: {state.current_stage.value}",
        f"Source language: {state.source_language} → {state.target_platform}",
    ]

    if state.scai_project_initialized:
        lines.append("✓ Project initialized")
    if state.scai_source_added:
        lines.append(f"✓ Source code added ({len(state.source_files)} files)")
    if state.scai_converted:
        lines.append(f"✓ Code converted ({len(state.converted_files)} output files)")

    if state.execution_passed:
        lines.append("✓ SQL execution passed")
    elif state.execution_errors:
        last_err = state.execution_errors[-1] if state.execution_errors else {}
        lines.append(f"✗ SQL execution failed: {last_err.get('type', 'unknown')} — {last_err.get('message', '')[:200]}")
        if state.missing_objects:
            lines.append(f"  Missing objects: {', '.join(state.missing_objects)}")

    if state.self_heal_iteration > 0:
        lines.append(f"Self-heal iterations: {state.self_heal_iteration}/{state.max_self_heal_iterations}")
        if state.self_heal_log:
            last_heal = state.self_heal_log[-1]
            lines.append(f"  Last heal: {'success' if last_heal.get('success') else 'failed'}")

    if state.validation_passed:
        lines.append("✓ Validation passed")
    elif state.validation_issues:
        lines.append(f"✗ Validation failed: {len(state.validation_issues)} issues")
        for issue in state.validation_issues[:3]:
            lines.append(f"  - [{issue.get('severity', 'error')}] {issue.get('message', '')[:100]}")

    if state.errors:
        lines.append(f"Errors ({len(state.errors)}):")
        for err in state.errors[-3:]:
            lines.append(f"  - {err[:150]}")

    if state.warnings:
        lines.append(f"Warnings: {len(state.warnings)} total")

    if state.report_scan_summary:
        summary = state.report_scan_summary
        lines.append(
            f"SnowConvert report: {summary.get('actionable_issues', 0)} actionable issues, "
            f"{summary.get('ignored_issues', 0)} ignored"
        )

    return "\n".join(lines)


def _build_supervisor_prompt(state: MigrationContext) -> str:
    """Build the full supervisor prompt for Snowflake Cortex."""
    stage = state.current_stage.value
    allowed = _ALLOWED_DECISIONS.get(stage, ["proceed", "abort"])
    natural_next = _NATURAL_NEXT.get(stage, "finalize")

    state_summary = _build_state_summary(state)

    return f"""You are a Snowflake migration workflow orchestrator. You evaluate the result of each workflow step and decide the next action.

CURRENT STATE:
{state_summary}

LAST COMPLETED STEP: {stage}

ALLOWED DECISIONS: {json.dumps(allowed)}
- "proceed": Continue to the natural next step ({natural_next})
- "self_heal": Route to LLM-based code repair (only if execution/validation failed)
- "human_review": Pause workflow for user intervention (e.g., missing DDL objects)
- "finalize": Skip remaining steps and finalize with current results
- "abort": Stop workflow due to unrecoverable error

RULES:
1. If the current step completed successfully with no errors, decide "proceed".
2. If execution failed due to a missing object (table/schema not found), decide "human_review".
3. If execution failed due to a syntax or logic error, decide "self_heal" (unless max iterations reached).
4. If validation failed and self-heal budget remains, decide "self_heal".
5. If validation failed and self-heal budget is exhausted, decide "finalize".
6. If there are critical unrecoverable errors, decide "abort".
7. Always explain your reasoning briefly.

Respond with ONLY a JSON object, no markdown fences:
{{"decision": "<one of {json.dumps(allowed)}>", "reasoning": "<brief explanation>"}}"""


def _parse_supervisor_response(raw: str, allowed: list[str]) -> tuple[str, str]:
    """Parse the LLM's JSON response into (decision, reasoning)."""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:]).strip()

    try:
        parsed = json.loads(text)
        decision = str(parsed.get("decision", "proceed")).strip().lower()
        reasoning = str(parsed.get("reasoning", "")).strip()

        if decision not in allowed:
            logger.warning("Supervisor returned invalid decision '%s', defaulting to 'proceed'", decision)
            decision = "proceed"

        return decision, reasoning

    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to parse supervisor response: %s. Raw: %s", e, text[:200])
        # Fallback: try to extract decision from text
        for option in allowed:
            if option in text.lower():
                return option, f"(Parsed from text) {text[:200]}"
        return "proceed", f"(Parse failed, defaulting to proceed) {text[:200]}"


def supervisor_node(state: MigrationContext) -> MigrationContext:
    """
    LLM Supervisor — the agentic brain.

    Calls Snowflake Cortex to evaluate the workflow state after each
    task node and decides the next action. Streams reasoning to frontend.
    """
    stage = state.current_stage.value
    allowed = _ALLOWED_DECISIONS.get(stage, ["proceed", "abort"])

    # Skip supervisor for ERROR/COMPLETED states
    if state.current_stage in (MigrationState.ERROR, MigrationState.COMPLETED):
        state.supervisor_decision = "finalize" if state.current_stage == MigrationState.ERROR else "proceed"
        state.supervisor_reasoning = f"Stage is {stage}, auto-routing."
        log_event(state, "info", f"[Supervisor] Auto-routing: {state.supervisor_decision}")
        return state

    # Skip supervisor if already in human review with intervention required
    if state.current_stage == MigrationState.HUMAN_REVIEW and state.requires_human_intervention:
        state.supervisor_decision = "human_review"
        state.supervisor_reasoning = "Human intervention is required. Pausing workflow."
        log_event(state, "info", "[Supervisor] Human review required, pausing.")
        return state

    logger.info("[Supervisor] Evaluating after stage: %s", stage)
    log_event(state, "info", f"[Supervisor] Evaluating after: {stage}")
    pty_echo(state.session_id, f"🧠 Supervisor evaluating after: {stage}...")

    try:
        from core.integrations import get_snowflake_session

        session = get_snowflake_session(state)
        if session is None:
            # Can't reach LLM — use deterministic fallback
            decision, reasoning = _deterministic_fallback(state, allowed)
            logger.warning("[Supervisor] No Snowflake session, using fallback: %s", decision)
        else:
            try:
                from langchain_community.chat_models.snowflake import ChatSnowflakeCortex

                model_name = (
                    os.getenv("SNOWFLAKE_CORTEX_MODEL")
                    or os.getenv("CORTEX_MODEL")
                    or "claude-4-sonnet"
                ).strip() or "claude-4-sonnet"

                chat_model = ChatSnowflakeCortex(
                    model=model_name,
                    cortex_function="complete",
                    session=session,
                    temperature=0,
                )

                prompt = _build_supervisor_prompt(state)
                response = chat_model.invoke(prompt)
                raw_text = str(response.content or "").strip()

                decision, reasoning = _parse_supervisor_response(raw_text, allowed)

            except Exception as llm_exc:
                logger.warning("[Supervisor] LLM call failed: %s, using fallback", llm_exc)
                decision, reasoning = _deterministic_fallback(state, allowed)
                reasoning = f"(LLM unavailable: {llm_exc}) {reasoning}"
            finally:
                try:
                    session.close()
                except Exception:
                    pass

        state.supervisor_decision = decision
        state.supervisor_reasoning = reasoning
        state.updated_at = datetime.now()

        log_event(state, "info", f"[Supervisor] Decision: {decision}", {"reasoning": reasoning})
        pty_echo(state.session_id, f"🧠 Supervisor → {decision}: {reasoning[:120]}")

        # Record in decision history
        state.decision_history.append({
            "timestamp": datetime.now().isoformat(),
            "after_stage": stage,
            "decision": decision,
            "reasoning": reasoning,
        })

    except Exception as e:
        error_msg = f"Supervisor exception: {e}"
        logger.error(error_msg)
        state.supervisor_decision = "proceed"
        state.supervisor_reasoning = f"(Error: {e}) Defaulting to proceed."
        log_event(state, "warning", f"[Supervisor] Error, defaulting: {error_msg}")

    return state


def _deterministic_fallback(state: MigrationContext, allowed: list[str]) -> tuple[str, str]:
    """
    Fallback routing when LLM is unavailable.

    Uses the same logic as the old conditional edges.
    """
    stage = state.current_stage.value

    if state.current_stage == MigrationState.ERROR:
        return "finalize", "Error state detected, finalizing."

    if stage == MigrationState.EXECUTE_SQL.value:
        if state.execution_passed:
            return "proceed", "Execution passed, proceeding to validation."
        if state.missing_objects and "human_review" in allowed:
            return "human_review", f"Missing objects: {', '.join(state.missing_objects)}"
        if "self_heal" in allowed:
            return "self_heal", "Execution failed, attempting self-heal."
        return "finalize", "Execution failed, no recovery options."

    if stage == MigrationState.VALIDATE.value:
        if state.validation_passed:
            return "proceed", "Validation passed."
        if state.self_heal_iteration < state.max_self_heal_iterations and "self_heal" in allowed:
            return "self_heal", f"Validation failed, self-heal iteration {state.self_heal_iteration + 1}."
        return "finalize", "Validation failed, max retries reached."

    if stage == MigrationState.SELF_HEAL.value:
        return "proceed", "Self-heal complete, proceeding to validation."

    # Linear stages: always proceed
    return "proceed", f"Step {stage} completed, proceeding."
