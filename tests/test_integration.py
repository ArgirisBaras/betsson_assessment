"""Integration tests — end-to-end pipeline tests with mocked LLM.

Tests the full flow: process email → classification → routing → draft/summarize/schedule → approval.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.schemas.email import EmailIntent, EmailLabel, EmailPriority


def test_edited_approval_learns_from_original_payload(monkeypatch):
    """Edited approvals should compare user edits against the original draft."""
    from app.api import approvals

    stored_preferences = []

    def fake_store_preference(preference):
        stored_preferences.append(preference)

    monkeypatch.setattr("app.memory.long_term.store_preference", fake_store_preference)

    approval = {
        "approval_id": "approval-regression-edit-learning",
        "action_type": "send_reply",
        "status": "pending",
        "description": "Approve drafted reply",
        "payload": {
            "to_addresses": ["user@example.com"],
            "subject": "Re: Status",
            "body": "Short neutral original draft.",
            "tone": "neutral",
            "thread_id": "thread-test",
        },
    }
    original_payload = dict(approval["payload"])
    edited_payload = {
        "body": "Hi, thanks for the detailed update. I appreciate the context and will follow up with the team today.",
        "tone": "friendly",
    }

    approval["payload"] = {**original_payload, **edited_payload}

    approvals._learn_from_edit(
        approval=approval,
        original_payload=original_payload,
        edited_payload=edited_payload,
        feedback="Please sound warmer in future replies.",
    )

    preference_by_key = {preference.key: preference for preference in stored_preferences}
    assert preference_by_key["preferred_reply_tone"].value == "friendly"
    assert "neutral" in preference_by_key["preferred_reply_tone"].description
    assert preference_by_key["reply_style_example"].value == edited_payload["body"][:500]
    assert preference_by_key["drafting_feedback"].value == "Please sound warmer in future replies."


# ── Helper: mock classification result ────────────────────────────────────────

def _mock_classified_email(intent="request", priority="urgent"):
    """Return a classification dict as produced by the reader agent."""
    return {
        "email": {},
        "intent": intent,
        "priority": priority,
        "confidence": 0.92,
        "suggested_labels": ["action_required"],
        "summary": f"Test {intent} email",
    }


# ── Integration: Full pipeline (urgent request → draft → approve) ────────────

@pytest.mark.asyncio
async def test_full_pipeline_urgent_request(client):
    """Process an urgent email end-to-end and verify draft + approval are created."""
    # Process email-001 (urgent production issue)
    response = await client.post("/inbox/process", json={"email_id": "email-001"})
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "completed"
    assert data["email_id"] == "email-001"

    # Should have classification
    assert data["classification"] is not None
    assert data["classification"]["intent"] in ("request", "question", "complaint")
    assert data["classification"]["priority"] in ("urgent", "high")

    # Should have generated a draft reply (urgent request → draft)
    assert data["draft_reply"] is not None
    assert data["draft_reply"]["to_addresses"] == ["sarah.chen@techcorp.com"]
    assert "Re:" in data["draft_reply"]["subject"]
    assert len(data["draft_reply"]["body"]) > 0

    # Should have a pending approval
    assert len(data["pending_approvals"]) >= 1
    approval = data["pending_approvals"][0]
    assert approval["action_type"] == "send_reply"
    assert approval["status"] == "pending"


@pytest.mark.asyncio
async def test_full_pipeline_fyi_email(client):
    """Process an FYI email — should summarize but NOT generate a draft reply."""
    response = await client.post("/inbox/process", json={"email_id": "email-005"})
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "completed"

    # Classification should be information/low
    assert data["classification"] is not None
    assert data["classification"]["intent"] in ("information", "feedback")

    # Should have a thread summary
    assert data["thread_summary"] is not None
    assert "summary" in data["thread_summary"]

    # Should NOT have a draft reply (FYI doesn't need a response)
    assert data["draft_reply"] is None


@pytest.mark.asyncio
async def test_full_pipeline_meeting_reminder(client):
    """Process a meeting/reminder email — should route to scheduler."""
    response = await client.post("/inbox/process", json={"email_id": "email-006"})
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "completed"
    assert data["classification"] is not None

    # Should schedule a follow-up (meeting_invite or follow_up intent)
    # The fallback classifier picks up "reminder" → follow_up
    if data["classification"]["intent"] in ("meeting_invite", "follow_up"):
        assert data["follow_up"] is not None
        assert data["follow_up"]["scheduled_at"] is not None


# ── Integration: Approval decide flow ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_approval_approve_sends_email(client):
    """Approve a draft and verify the email is 'sent'."""
    # First, process an email to create an approval
    resp = await client.post("/inbox/process", json={"email_id": "email-001"})
    assert resp.status_code == 200
    data = resp.json()

    # Get the approval ID
    assert len(data["pending_approvals"]) >= 1
    approval_id = data["pending_approvals"][0]["approval_id"]

    # Approve it
    resp = await client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approved", "feedback": "Looks good"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["decision"] == "approved"
    assert result["execution"]["status"] == "sent"
    assert "email_id" in result["execution"]


@pytest.mark.asyncio
async def test_approval_reject(client):
    """Reject a pending approval — action should be cancelled."""
    # Process email to create approval
    resp = await client.post("/inbox/process", json={"email_id": "email-004"})
    assert resp.status_code == 200
    data = resp.json()

    if not data["pending_approvals"]:
        pytest.skip("No approvals generated for this email")

    approval_id = data["pending_approvals"][0]["approval_id"]

    # Reject it
    resp = await client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "rejected", "feedback": "Not appropriate"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["decision"] == "rejected"
    assert result["execution"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_approval_edit_and_approve(client):
    """Edit a draft payload and approve — should use modified content."""
    # Process email to create approval
    resp = await client.post("/inbox/process", json={"email_id": "email-001"})
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["pending_approvals"]) >= 1
    approval_id = data["pending_approvals"][0]["approval_id"]

    # Edit and approve
    edited_body = "Custom edited reply body for testing."
    resp = await client.post(
        f"/approvals/{approval_id}/decide",
        json={
            "decision": "edited",
            "edited_payload": {"body": edited_body},
            "feedback": "Rewrote the reply",
        },
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["decision"] == "edited"
    assert result["execution"]["status"] == "sent"


@pytest.mark.asyncio
async def test_approval_cannot_decide_twice(client):
    """Attempting to decide on an already-decided approval should fail."""
    # Process and approve
    resp = await client.post("/inbox/process", json={"email_id": "email-001"})
    data = resp.json()
    approval_id = data["pending_approvals"][0]["approval_id"]

    await client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approved", "feedback": ""},
    )

    # Try again
    resp = await client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approved", "feedback": ""},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_send_reply_approval_metrics_are_action_specific(client):
    """Approving a draft reply should update generic, reply, and legacy draft metrics."""
    await client.post("/reset")

    resp = await client.post("/inbox/process", json={"email_id": "email-001"})
    assert resp.status_code == 200
    data = resp.json()
    approval_id = data["pending_approvals"][0]["approval_id"]

    resp = await client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approved", "feedback": "Looks good"},
    )
    assert resp.status_code == 200

    counters = (await client.get("/metrics")).json()["counters"]
    assert counters["approvals_approved"] == 1
    assert counters["send_replies_approved"] == 1
    assert counters["drafts_approved"] == 1
    assert counters["follow_ups_approved"] == 0


@pytest.mark.asyncio
async def test_follow_up_approval_metrics_do_not_increment_draft_counters(client):
    """Approving a follow-up should not masquerade as a draft approval."""
    await client.post("/reset")

    resp = await client.post("/inbox/process", json={"email_id": "email-006"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_approvals"]
    approval_id = data["pending_approvals"][0]["approval_id"]
    assert data["pending_approvals"][0]["action_type"] == "schedule_followup"

    resp = await client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "approved", "feedback": "Schedule it"},
    )
    assert resp.status_code == 200

    counters = (await client.get("/metrics")).json()["counters"]
    assert counters["approvals_approved"] == 1
    assert counters["follow_ups_approved"] == 1
    assert counters["follow_ups_scheduled"] == 1
    assert counters["send_replies_approved"] == 0
    assert counters["drafts_approved"] == 0


# ── Integration: Memory search ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_contacts_search(client):
    """Test searching contacts in long-term memory."""
    response = await client.get("/memory/contacts/search", params={"q": "sarah"})
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


@pytest.mark.asyncio
async def test_memory_preferences_list(client):
    """Test listing preferences from long-term memory."""
    response = await client.get("/memory/preferences")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "preferences" in data


@pytest.mark.asyncio
async def test_memory_add_preference(client):
    """Test adding a new preference to long-term memory."""
    response = await client.post("/memory/preferences", json={
        "key": "test_reply_tone",
        "value": "casual",
        "description": "Use casual tone for test emails",
    })
    assert response.status_code in (200, 201)


# ── Integration: Metrics accumulate ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_metrics_increment_after_processing(client):
    """Verify metrics counters increase after processing emails."""
    # Get baseline
    resp = await client.get("/metrics")
    baseline = resp.json()
    baseline_processed = baseline["counters"]["emails_processed"]

    # Process an email
    await client.post("/inbox/process", json={"email_id": "email-001"})

    # Check metrics increased
    resp = await client.get("/metrics")
    after = resp.json()
    assert after["counters"]["emails_processed"] > baseline_processed
    assert after["counters"]["emails_classified"] > baseline["counters"]["emails_classified"]


# ── Integration: Traces are recorded ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_traces_recorded_after_processing(client):
    """Verify that processing an email creates a trace."""
    # Process an email
    await client.post("/inbox/process", json={"email_id": "email-001"})

    # Check traces
    resp = await client.get("/traces")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["traces"]) >= 1

    # Verify trace structure
    trace = data["traces"][-1]
    assert "run_id" in trace
    assert "spans" in trace
    assert len(trace["spans"]) >= 1


# ── Integration: Process nonexistent email ───────────────────────────────────

@pytest.mark.asyncio
async def test_process_nonexistent_email(client):
    """Processing a non-existent email should return 404."""
    response = await client.post("/inbox/process", json={"email_id": "does-not-exist"})
    assert response.status_code == 404


# ── Integration: Reset endpoint ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_clears_state(client):
    """POST /reset should clear metrics, traces, and approvals."""
    # Process something first
    await client.post("/inbox/process", json={"email_id": "email-001"})

    # Reset
    resp = await client.post("/reset")
    assert resp.status_code == 200
    assert resp.json()["status"] == "reset_complete"

    # Verify metrics are reset
    resp = await client.get("/metrics")
    counters = resp.json()["counters"]
    assert counters["emails_processed"] == 0

    # Verify traces are cleared
    resp = await client.get("/traces")
    assert resp.json()["total"] == 0

    # Verify approvals are cleared
    resp = await client.get("/approvals/")
    assert resp.json()["total"] == 0


# ── Integration: Memory feedback loop (behavior evolution) ───────────────────

@pytest.mark.asyncio
async def test_feedback_loop_edit_stores_preference(client):
    """Editing a draft should store feedback in long-term memory."""
    # Process email to create a draft approval
    resp = await client.post("/inbox/process", json={"email_id": "email-001"})
    data = resp.json()
    assert len(data["pending_approvals"]) >= 1
    approval_id = data["pending_approvals"][0]["approval_id"]

    # Edit with feedback — this should trigger memory learning
    resp = await client.post(
        f"/approvals/{approval_id}/decide",
        json={
            "decision": "edited",
            "edited_payload": {"body": "Completely different reply written by the user."},
            "feedback": "Make replies shorter and more direct.",
        },
    )
    assert resp.status_code == 200

    # Verify the feedback was stored in long-term memory
    resp = await client.get("/memory/preferences/search", params={"q": "shorter direct"})
    assert resp.status_code == 200
    results = resp.json().get("results", [])
    assert any("shorter" in r["document"].lower() or "direct" in r["document"].lower() for r in results)


@pytest.mark.asyncio
async def test_feedback_loop_rejection_stores_reason(client):
    """Rejecting an approval with feedback should store it as a preference."""
    # Process email to create approval
    resp = await client.post("/inbox/process", json={"email_id": "email-004"})
    data = resp.json()

    if not data["pending_approvals"]:
        pytest.skip("No approvals generated")

    approval_id = data["pending_approvals"][0]["approval_id"]

    # Reject with feedback
    resp = await client.post(
        f"/approvals/{approval_id}/decide",
        json={
            "decision": "rejected",
            "feedback": "Never reply to partner-brand emails automatically.",
        },
    )
    assert resp.status_code == 200

    # Verify rejection feedback was stored
    resp = await client.get("/memory/preferences/search", params={"q": "partner-brand automatically"})
    assert resp.status_code == 200
    results = resp.json().get("results", [])
    assert any("partner-brand" in r["document"].lower() or "automatically" in r["document"].lower() for r in results)


