"""Tests for the orchestrator graph construction."""

import pytest

from app.agents.orchestrator import build_graph, route_after_classification
from app.agents.reader import _route_email
from app.memory.short_term import build_initial_state


def test_build_graph():
    """Test that the graph compiles successfully."""
    graph = build_graph()
    compiled = graph.compile()
    assert compiled is not None


def test_initial_state():
    """Test building initial agent state."""
    state = build_initial_state()
    assert state["messages"] == []
    assert state["current_email"] is None
    assert state["pending_approvals"] == []
    assert state["errors"] == []


def test_route_email_urgent_request():
    """Test routing for urgent requests → draft."""
    assert _route_email("request", "urgent") == "draft"


def test_route_email_question():
    """Test routing for questions → draft."""
    assert _route_email("question", "normal") == "draft"


def test_route_email_meeting():
    """Test routing for meeting invites → schedule."""
    assert _route_email("meeting_invite", "normal") == "schedule"


def test_route_email_follow_up():
    """Test routing for follow-ups → schedule."""
    assert _route_email("follow_up", "normal") == "schedule"


def test_route_email_information():
    """Test routing for information → summarize."""
    assert _route_email("information", "low") == "summarize"


def test_route_email_spam():
    """Test routing for spam → end."""
    assert _route_email("spam", "low") == "end"


def test_route_after_classification():
    """Test the conditional edge routing function."""
    assert route_after_classification({"next_action": "draft"}) == "draft"
    assert route_after_classification({"next_action": "summarize"}) == "summarize"
    assert route_after_classification({"next_action": "schedule"}) == "schedule"
    assert route_after_classification({"next_action": "end"}) == "end"

