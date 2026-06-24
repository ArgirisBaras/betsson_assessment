"""Short-term memory — conversation context within a single processing run.

Short-term memory is implemented directly via the LangGraph AgentState TypedDict.
This module provides helper functions for managing the state window,
truncating context, and extracting relevant information.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


def build_initial_state() -> dict[str, Any]:
    """Create a fresh AgentState with default values."""
    return {
        "messages": [],
        "current_email": None,
        "classification": None,
        "thread_summary": None,
        "draft_reply": None,
        "follow_up": None,
        "pending_approvals": [],
        "completed_actions": [],
        "memory_context": [],
        "next_action": "",
        "run_id": "",
        "errors": [],
    }


def add_system_context(state: dict, context: str) -> dict:
    """Add a system message with context to the message history."""
    state["messages"] = state.get("messages", []) + [
        SystemMessage(content=context)
    ]
    return state


def get_context_window(state: dict, max_messages: int = 20) -> list:
    """Return the most recent messages (sliding window for token management)."""
    messages = state.get("messages", [])
    if len(messages) <= max_messages:
        return messages
    # Always keep the first system message + last N messages
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    recent = messages[-max_messages:]
    if system_msgs and system_msgs[0] not in recent:
        return [system_msgs[0]] + recent
    return recent


def format_state_summary(state: dict) -> str:
    """Create a human-readable summary of current processing state."""
    parts = []
    if state.get("current_email"):
        email = state["current_email"]
        parts.append(f"Processing email: {email.get('subject', 'N/A')} from {email.get('from_address', 'N/A')}")
    if state.get("classification"):
        cls = state["classification"]
        parts.append(f"Classification: {cls.get('intent', 'N/A')} (priority: {cls.get('priority', 'N/A')})")
    if state.get("thread_summary"):
        parts.append("Thread summary: generated")
    if state.get("draft_reply"):
        parts.append("Draft reply: ready for approval")
    if state.get("follow_up"):
        parts.append("Follow-up: scheduled")
    if state.get("pending_approvals"):
        parts.append(f"Pending approvals: {len(state['pending_approvals'])}")
    if state.get("errors"):
        parts.append(f"Errors: {len(state['errors'])}")
    return " | ".join(parts) if parts else "No active processing"

