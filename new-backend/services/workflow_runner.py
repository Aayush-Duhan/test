"""
Workflow runner — executes the LangGraph migration workflow asynchronously
and yields data_stream SSE events for real-time frontend updates.

Bridges MigrationContext state with the data_stream protocol,
wiring activity_log_sink for live event streaming.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

from graph.state import MigrationContext, MigrationState
from graph.scai_workflow import build_migration_graph
from stream.data_stream import DataStreamBuilder, format_sse_data

logger = logging.getLogger(__name__)

# In-memory store for active workflow runs
_runs: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Step display names
# ============================================================================

STEP_DISPLAY_NAMES = {
    "init_project": "Initialize Project",
    "add_source_code": "Add Source Code",
    "apply_schema_mapping": "Apply Schema Mapping",
    "convert_code": "Convert Code",
    "execute_sql": "Execute SQL",
    "self_heal": "Self-Heal",
    "validate": "Validate",
    "human_review": "Human Review",
    "finalize": "Finalize",
}

ALL_STEPS = [
    "init_project", "add_source_code", "apply_schema_mapping",
    "convert_code", "execute_sql", "self_heal", "validate",
    "human_review", "finalize",
]


def _build_workflow_status(
    run_id: str,
    ctx: MigrationContext,
    current_node: Optional[str] = None,
    overall_status: str = "running",
) -> Dict[str, Any]:
    """Build a workflow-status data part for SSE streaming."""
    stage_value = ctx.current_stage.value if ctx.current_stage else "idle"

    # Determine which steps have been reached
    steps = []
    reached_current = False
    for step_id in ALL_STEPS:
        if step_id == current_node:
            status = "running"
            reached_current = True
        elif not reached_current:
            status = "completed"
        else:
            status = "pending"

        # Override with error state
        if ctx.current_stage == MigrationState.ERROR and step_id == current_node:
            status = "failed"

        # Override with completed state
        if overall_status == "completed":
            status = "completed"
        elif overall_status == "failed" and step_id == current_node:
            status = "failed"

        steps.append({
            "id": step_id,
            "name": STEP_DISPLAY_NAMES.get(step_id, step_id),
            "status": status,
            "message": _get_step_message(ctx, step_id, status),
        })

    return {
        "runId": run_id,
        "status": overall_status,
        "currentStep": current_node,
        "stage": stage_value,
        "steps": steps,
    }


def _get_step_message(ctx: MigrationContext, step_id: str, status: str) -> Optional[str]:
    """Generate a contextual message for a step based on current state."""
    if status == "pending":
        return None

    if step_id == "execute_sql" and not ctx.execution_passed and ctx.execution_errors:
        last_error = ctx.execution_errors[-1] if ctx.execution_errors else {}
        return last_error.get("message", "")[:100] if last_error else None

    if step_id == "self_heal" and ctx.self_heal_iteration > 0:
        return f"Iteration {ctx.self_heal_iteration}/{ctx.max_self_heal_iterations}"

    if step_id == "validate" and ctx.validation_issues:
        return f"{len(ctx.validation_issues)} issues found"

    if step_id == "human_review" and ctx.human_intervention_reason:
        return ctx.human_intervention_reason[:100]

    if step_id == "finalize" and status == "completed":
        return f"{len(ctx.output_files)} files output"

    return None


# ============================================================================
# Workflow lifecycle
# ============================================================================

def start_workflow(
    run_id: str,
    ctx: MigrationContext,
) -> None:
    """Register a new workflow run."""
    ctx.run_id = run_id
    _runs[run_id] = {
        "ctx": ctx,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "paused": False,
    }
    logger.info("Workflow run registered: %s", run_id)


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Get a workflow run by ID."""
    return _runs.get(run_id)


def get_run_status(run_id: str) -> Optional[Dict[str, Any]]:
    """Get the current status of a workflow run."""
    run = _runs.get(run_id)
    if not run:
        return None
    ctx: MigrationContext = run["ctx"]
    return {
        "run_id": run_id,
        "status": run["status"],
        "stage": ctx.current_stage.value,
        "paused": run.get("paused", False),
        "requires_human_intervention": ctx.requires_human_intervention,
        "human_intervention_reason": ctx.human_intervention_reason,
        "errors": ctx.errors[-5:],
        "warnings_count": len(ctx.warnings),
        "self_heal_iteration": ctx.self_heal_iteration,
        "summary_report": ctx.summary_report if ctx.current_stage == MigrationState.COMPLETED else None,
    }


async def run_workflow_stream(run_id: str) -> AsyncGenerator[str, None]:
    """
    Execute the LangGraph workflow and yield SSE events.

    This is the core streaming function consumed by the /api/scai/run/{run_id} endpoint.
    It:
    1. Compiles the LangGraph
    2. Wires activity_log_sink for real-time event emission
    3. Streams node execution events as data-workflow-status parts
    4. Handles human_review pauses
    """
    run = _runs.get(run_id)
    if not run:
        yield format_sse_data({"type": "error", "error": {"message": "Run not found"}})
        return

    ctx: MigrationContext = run["ctx"]
    run["status"] = "running"
    builder = DataStreamBuilder()

    # Event queue for activity_log_sink → SSE bridge
    event_queue: asyncio.Queue = asyncio.Queue()

    def activity_sink(entry: Dict[str, Any]) -> None:
        """Push activity log entries to the async queue for SSE streaming."""
        try:
            event_queue.put_nowait(entry)
        except Exception:
            pass

    ctx.activity_log_sink = activity_sink

    # Emit initial status
    status_data = _build_workflow_status(run_id, ctx, current_node="init_project")
    yield format_sse_data({"type": "data", "data": [status_data]})

    try:
        compiled_graph = build_migration_graph()
        initial_state = {"ctx": ctx}

        # Run graph with streaming
        current_node = None
        last_task_node = "init_project"
        async for event in compiled_graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_output in event.items():
                current_node = node_name

                # Update context from output
                if isinstance(node_output, dict) and "ctx" in node_output:
                    ctx = node_output["ctx"]
                    run["ctx"] = ctx

                # Skip supervisor from step status — emit its reasoning instead
                if node_name == "supervisor":
                    if ctx.supervisor_reasoning:
                        supervisor_event = {
                            "type": "supervisor_reasoning",
                            "runId": run_id,
                            "afterStep": ctx.current_stage.value,
                            "decision": ctx.supervisor_decision,
                            "reasoning": ctx.supervisor_reasoning,
                        }
                        yield format_sse_data({"type": "data", "data": [supervisor_event]})

                        # Also emit as reasoning delta for text display
                        reasoning_id = builder.new_reasoning_id()
                        msg = f"🧠 Supervisor → **{ctx.supervisor_decision}**: {ctx.supervisor_reasoning}\n"
                        part = builder.create_reasoning_delta(reasoning_id, msg)
                        yield format_sse_data(part)
                    continue  # Don't emit step status for supervisor itself

                # Track the last task node for status display
                last_task_node = node_name

                # Determine overall status
                if ctx.current_stage == MigrationState.ERROR:
                    overall = "failed"
                elif ctx.current_stage == MigrationState.COMPLETED:
                    overall = "completed"
                elif ctx.current_stage == MigrationState.HUMAN_REVIEW:
                    overall = "running"
                else:
                    overall = "running"

                # Emit workflow status update
                status_data = _build_workflow_status(run_id, ctx, last_task_node, overall)
                yield format_sse_data({"type": "data", "data": [status_data]})

                # Emit any queued activity log entries as reasoning deltas
                while not event_queue.empty():
                    try:
                        entry = event_queue.get_nowait()
                        reasoning_id = builder.new_reasoning_id()
                        msg = f"[{entry.get('level', 'info').upper()}] {entry.get('message', '')}"
                        part = builder.create_reasoning_delta(reasoning_id, msg + "\n")
                        yield format_sse_data(part)
                    except asyncio.QueueEmpty:
                        break

                # Handle human review pause
                if ctx.current_stage == MigrationState.HUMAN_REVIEW and ctx.requires_human_intervention:
                    run["paused"] = True
                    run["status"] = "paused"
                    pause_data = {
                        "type": "human_review_required",
                        "run_id": run_id,
                        "reason": ctx.human_intervention_reason,
                        "missing_objects": ctx.missing_objects,
                        "requires_ddl_upload": ctx.requires_ddl_upload,
                    }
                    yield format_sse_data({"type": "data", "data": [pause_data]})
                    # Stream will end here; client must call /resume after uploading DDL
                    return

        # Final status
        if ctx.current_stage == MigrationState.COMPLETED:
            run["status"] = "completed"
            final_status = _build_workflow_status(run_id, ctx, "finalize", "completed")
        elif ctx.current_stage == MigrationState.ERROR:
            run["status"] = "failed"
            final_status = _build_workflow_status(run_id, ctx, current_node, "failed")
        else:
            run["status"] = "completed"
            final_status = _build_workflow_status(run_id, ctx, current_node, "completed")

        yield format_sse_data({"type": "data", "data": [final_status]})

        # Emit summary as text if completed
        if ctx.summary_report:
            text_id = builder.new_text_id()
            summary_text = f"\n\n**Migration Complete!** Output: `{ctx.output_path}`\n"
            summary_text += f"- Files: {len(ctx.output_files)}\n"
            summary_text += f"- Self-heal iterations: {ctx.self_heal_iteration}\n"
            summary_text += f"- Validation: {'Passed' if ctx.validation_passed else 'Failed'}\n"
            yield format_sse_data(builder.create_text_delta(text_id, summary_text))

    except Exception as exc:
        run["status"] = "failed"
        logger.error("Workflow execution failed: %s", exc, exc_info=True)
        error_part = {"type": "error", "error": {"message": str(exc)}}
        yield format_sse_data(error_part)

    finally:
        ctx.activity_log_sink = None


async def resume_workflow_stream(run_id: str) -> AsyncGenerator[str, None]:
    """
    Resume a paused workflow after human review.

    Re-runs the graph from execute_sql with the updated context.
    """
    run = _runs.get(run_id)
    if not run:
        yield format_sse_data({"type": "error", "error": {"message": "Run not found"}})
        return

    ctx: MigrationContext = run["ctx"]
    run["paused"] = False
    run["status"] = "running"

    # Reset human review flags
    ctx.requires_human_intervention = False
    ctx.current_stage = MigrationState.EXECUTE_SQL

    # Re-stream the workflow
    async for event in run_workflow_stream(run_id):
        yield event
