"""Tests for individual agent functions."""

from datetime import datetime

from app.schemas.email import EmailMessage
from app.tools.classifier import _fallback_classify


def _make_email(**kwargs) -> EmailMessage:
    """Helper to create a test email."""
    defaults = {
        "id": "test-001",
        "thread_id": "thread-test",
        "from_address": "test@example.com",
        "to_addresses": ["user@company.com"],
        "subject": "Test Subject",
        "body": "Test body",
        "timestamp": datetime(2026, 6, 23, 12, 0, 0),
    }
    defaults.update(kwargs)
    return EmailMessage(**defaults)


def test_fallback_classify_urgent():
    """Test fallback classifier detects urgent emails."""
    email = _make_email(subject="URGENT: Server down", body="Production server is down, need help ASAP")
    result = _fallback_classify(email)
    assert result.priority.value == "urgent"
    assert result.intent.value == "request"


def test_fallback_classify_meeting():
    """Test fallback classifier detects meeting invites."""
    email = _make_email(subject="Meeting invite: Sprint planning", body="You're invited to the sprint planning meeting")
    result = _fallback_classify(email)
    assert result.intent.value == "meeting_invite"


def test_fallback_classify_question():
    """Test fallback classifier detects questions."""
    email = _make_email(subject="How to deploy the model?", body="I need help with deployment")
    result = _fallback_classify(email)
    assert result.intent.value == "question"


def test_fallback_classify_fyi():
    """Test fallback classifier detects FYI emails."""
    email = _make_email(subject="FYI: New policy update", body="For your information, the policy has been updated")
    result = _fallback_classify(email)
    assert result.intent.value == "information"
    assert result.priority.value == "low"


def test_fallback_classify_fyi_policy_with_schedule_wording():
    """Explicit FYI policy updates should not be misclassified as meetings."""
    email = _make_email(
        subject="FYI: Updated Remote Work Policy",
        body="Hybrid schedule: minimum 2 days in office per week.",
    )
    result = _fallback_classify(email)
    assert result.intent.value == "information"
    assert result.priority.value == "low"


def test_fallback_classify_follow_up():
    """Test fallback classifier detects follow-ups."""
    email = _make_email(subject="Following up on our discussion", body="Just checking in on the status")
    result = _fallback_classify(email)
    assert result.intent.value == "follow_up"

