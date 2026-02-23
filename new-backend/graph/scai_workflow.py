"""
LangGraph StateGraph — hub-and-spoke supervisor topology.

Every task node routes to the LLM supervisor, which evaluates
the state and decides the next action. The supervisor's decision
drives the conditional edge that routes to the next task node.

Topology:
  ┌──────────────────────────────────────────────────────┐
  │  init → SUP → add_source → SUP → schema_map → SUP   │
  │  → convert → SUP → execute_sql → SUP ──┬─→ validate │
  │                                         ├─→ self_heal│
  │                                         ├─→ human_rev│
  │                                         └─→ finalize │
  │  validate → SUP ──┬─→ finalize                       │
  │                    └─→ self_heal → SUP → validate     │
  │  human_review → SUP → execute_sql                     │
  │  finalize → END                                       │
  └──────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from graph.state import MigrationContext, MigrationState
from graph.nodes.init_project import init_project_node
from graph.nodes.add_source_code import add_source_code_node
from graph.nodes.apply_schema_mapping import apply_schema_mapping_node
from graph.nodes.convert_code import convert_code_node
from graph.nodes.execute_sql import execute_sql_node
from graph.nodes.self_heal import self_heal_node
from graph.nodes.validate import validate_node
from graph.nodes.human_review import human_review_node
from graph.nodes.finalize import finalize_node
from graph.nodes.supervisor import supervisor_node

logger = logging.getLogger(__name__)

# Maps stage → natural "proceed" target for the supervisor decision
_PROCEED_TARGET = {
    MigrationState.INIT_PROJECT.value: "add_source_code",
    MigrationState.ADD_SOURCE_CODE.value: "apply_schema_mapping",
    MigrationState.APPLY_SCHEMA_MAPPING.value: "convert_code",
    MigrationState.CONVERT_CODE.value: "execute_sql",
    MigrationState.EXECUTE_SQL.value: "validate",
    MigrationState.SELF_HEAL.value: "validate",
    MigrationState.VALIDATE.value: "finalize",
    MigrationState.HUMAN_REVIEW.value: "execute_sql",
    MigrationState.FINALIZE.value: END,
}


# ============================================================================
# Supervisor conditional edge
# ============================================================================

def route_after_supervisor(state: dict) -> str:
    """
    Route based on the supervisor's LLM decision.

    The supervisor sets `supervisor_decision` which is one of:
      proceed, self_heal, human_review, finalize, abort

    "proceed" resolves to the natural next node for the current stage.
    """
    ctx: MigrationContext = state["ctx"]
    decision = ctx.supervisor_decision
    stage = ctx.current_stage.value

    # Hard abort → finalize
    if decision == "abort":
        ctx.current_stage = MigrationState.ERROR
        ctx.errors.append(f"Supervisor aborted: {ctx.supervisor_reasoning}")
        return "finalize"

    # Explicit routing
    if decision == "self_heal":
        return "self_heal"
    if decision == "human_review":
        return "human_review"
    if decision == "finalize":
        return "finalize"

    # "proceed" — go to natural next step
    target = _PROCEED_TARGET.get(stage, "finalize")
    if target == END:
        return END
    return target


# ============================================================================
# Graph builder
# ============================================================================

def _w(node_fn):
    """Wrap a node function for dict-based LangGraph state."""
    def wrapper(state: dict) -> dict:
        ctx: MigrationContext = state["ctx"]
        updated = node_fn(ctx)
        return {"ctx": updated}
    wrapper.__name__ = node_fn.__name__
    return wrapper


def build_migration_graph() -> StateGraph:
    """
    Build and compile the supervisor-driven migration graph.

    Every task node → supervisor → conditional routing.
    """
    graph = StateGraph(dict)

    # ── Register task nodes ──
    graph.add_node("init_project", _w(init_project_node))
    graph.add_node("add_source_code", _w(add_source_code_node))
    graph.add_node("apply_schema_mapping", _w(apply_schema_mapping_node))
    graph.add_node("convert_code", _w(convert_code_node))
    graph.add_node("execute_sql", _w(execute_sql_node))
    graph.add_node("self_heal", _w(self_heal_node))
    graph.add_node("validate", _w(validate_node))
    graph.add_node("human_review", _w(human_review_node))
    graph.add_node("finalize", _w(finalize_node))

    # ── Register supervisor node ──
    graph.add_node("supervisor", _w(supervisor_node))

    # ── Entry point ──
    graph.set_entry_point("init_project")

    # ── Every task node flows into the supervisor ──
    graph.add_edge("init_project", "supervisor")
    graph.add_edge("add_source_code", "supervisor")
    graph.add_edge("apply_schema_mapping", "supervisor")
    graph.add_edge("convert_code", "supervisor")
    graph.add_edge("execute_sql", "supervisor")
    graph.add_edge("self_heal", "supervisor")
    graph.add_edge("validate", "supervisor")
    graph.add_edge("human_review", "supervisor")

    # ── Finalize goes to END (no supervisor needed) ──
    graph.add_edge("finalize", END)

    # ── Supervisor routes based on LLM decision ──
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "add_source_code": "add_source_code",
            "apply_schema_mapping": "apply_schema_mapping",
            "convert_code": "convert_code",
            "execute_sql": "execute_sql",
            "self_heal": "self_heal",
            "validate": "validate",
            "human_review": "human_review",
            "finalize": "finalize",
            END: END,
        },
    )

    return graph.compile()
