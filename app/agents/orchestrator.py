"""Orchestrator — LangGraph StateGraph that coordinates all worker agents.

Implements the main processing pipeline:
  read → classify → route → {summarize, draft, schedule} → HITL approval

Uses conditional edges for dynamic routing based on classification results.
"""

from __future__ import annotations

from typing import Literal

import structlog
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.schemas.agent import AgentState
from app.agents.reader import reader_node
from app.agents.summarizer import summarizer_node
from app.agents.drafter import drafter_node
from app.agents.scheduler import scheduler_node

logger = structlog.get_logger(__name__)


# ── Routing logic ────────────────────────────────────────────────────────────

def route_after_classification(state: dict) -> str:
    """Conditional edge: decide which agent(s) to invoke after classification."""
    next_action = state.get("next_action", "end")
    logger.info("routing_decision", next_action=next_action)

    if next_action == "draft":
        return "draft"
    elif next_action == "summarize":
        return "summarize"
    elif next_action == "schedule":
        return "schedule"
    elif next_action == "summarize_and_draft":
        return "summarize"  # summarize first, then draft
    elif next_action == "end":
        return "end"
    else:
        return "summarize"


def route_after_summarize(state: dict) -> str:
    """Conditional edge: after summarization, check if drafting is also needed."""
    next_action = state.get("next_action", "")
    if next_action == "summarize_and_draft":
        return "draft"
    return "end"


def route_after_draft(state: dict) -> str:
    """After drafting, check if scheduling is also needed."""
    classification = state.get("classification", {})
    intent = classification.get("intent", "")
    # If it's a meeting invite or follow-up, also schedule
    if intent in ("meeting_invite", "follow_up"):
        return "schedule"
    return "end"


# ── Graph construction ───────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Construct the LangGraph orchestrator graph.

    Returns a compiled graph with checkpointing support.

    Graph structure:
        reader → [route] → summarizer → [route] → drafter → [route] → scheduler → end
                        ↘ drafter → ...
                        ↘ scheduler → end
                        ↘ end
    """
    workflow = StateGraph(AgentState)

    # Add nodes (worker agents)
    workflow.add_node("reader", reader_node)
    workflow.add_node("summarize", summarizer_node)
    workflow.add_node("draft", drafter_node)
    workflow.add_node("schedule", scheduler_node)

    # Set entry point
    workflow.set_entry_point("reader")

    # Add conditional edges
    workflow.add_conditional_edges(
        "reader",
        route_after_classification,
        {
            "draft": "draft",
            "summarize": "summarize",
            "schedule": "schedule",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "summarize",
        route_after_summarize,
        {
            "draft": "draft",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "draft",
        route_after_draft,
        {
            "schedule": "schedule",
            "end": END,
        },
    )

    workflow.add_edge("schedule", END)

    return workflow


# ── Compiled graph singleton ─────────────────────────────────────────────────

_checkpointer = MemorySaver()
_graph = build_graph().compile(checkpointer=_checkpointer)


def get_graph():
    """Return the compiled orchestrator graph."""
    return _graph


def get_checkpointer():
    """Return the checkpointer for state inspection."""
    return _checkpointer


async def process_email(email_data: dict, thread_id: str = "default", run_id: str = "") -> dict:
    """Process a single email through the orchestrator pipeline.

    Args:
        email_data: EmailMessage as a dict
        thread_id: Unique thread ID for checkpointing
        run_id: Trace run ID for scoped observability

    Returns:
        Final agent state after processing. If a fatal error occurs,
        returns a state with the error captured rather than raising.
    """
    from app.memory.short_term import build_initial_state

    initial_state = build_initial_state()
    initial_state["current_email"] = email_data
    initial_state["run_id"] = run_id

    config = {"configurable": {"thread_id": thread_id}}

    logger.info("orchestrator_processing_started", email_id=email_data.get("id"))

    try:
        result = await _graph.ainvoke(initial_state, config=config)
    except Exception as exc:
        # Graceful degradation: capture the error in state instead of crashing
        logger.error(
            "orchestrator_fatal_error",
            email_id=email_data.get("id"),
            error=str(exc),
        )
        result = dict(initial_state)
        result["errors"] = [f"Pipeline error: {str(exc)}"]
        result["next_action"] = "end"
        return result

    logger.info(
        "orchestrator_processing_completed",
        email_id=email_data.get("id"),
        next_action=result.get("next_action"),
        pending_approvals=len(result.get("pending_approvals", [])),
        errors=len(result.get("errors", [])),
    )

    return result

