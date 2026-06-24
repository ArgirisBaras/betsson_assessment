"""Scheduler agent — creates follow-up reminders and calendar events.

Determines appropriate follow-up timing based on email priority
and user preferences, then creates calendar events with HITL approval.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from langchain_core.messages import AIMessage

from app.observability.metrics import metrics
from app.observability.tracing import get_latest_tracer
from app.schemas.actions import ActionType, ApprovalRequest, FollowUp

logger = structlog.get_logger(__name__)


async def scheduler_node(state: dict) -> dict:
    """LangGraph node: schedule follow-ups or reminders.

    Analyzes the email and classification to determine if/when
    a follow-up is needed, then creates an approval request.
    """
    logger.info("scheduler_agent_started")
    tracer = get_latest_tracer()
    span = tracer.start_span("agent", "scheduler") if tracer else None

    email_data = state.get("current_email")
    if not email_data:
        return {
            "errors": state.get("errors", []) + ["No email for scheduling"],
            "messages": [AIMessage(content="Error: No email to schedule follow-up for.")],
        }

    classification = state.get("classification", {})
    priority = classification.get("priority", "normal")
    intent = classification.get("intent", "information")
    start_time = time.time()

    # Determine follow-up timing based on priority and preferences
    follow_up_hours = _determine_follow_up_hours(priority, intent, state.get("memory_context", []))
    scheduled_at = datetime.now(timezone.utc) + timedelta(hours=follow_up_hours)

    # Build follow-up description
    description = _build_follow_up_description(email_data, classification)

    follow_up = FollowUp(
        email_id=email_data["id"],
        thread_id=email_data["thread_id"],
        scheduled_at=scheduled_at,
        description=description,
        assignee="user",
    )

    # Create approval request for the follow-up
    approval = ApprovalRequest(
        approval_id=f"apr-{uuid.uuid4().hex[:8]}",
        action_type=ActionType.SCHEDULE_FOLLOWUP,
        description=f"Schedule follow-up for: {email_data['subject']}",
        payload=follow_up.model_dump(mode="json"),
        email_id=email_data["id"],
        thread_id=email_data["thread_id"],
        created_at=datetime.now(timezone.utc),
    )

    schedule_msg = (
        f"⏰ Follow-up Scheduled:\n"
        f"  For: {email_data['subject']}\n"
        f"  When: {scheduled_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"  Description: {description}\n"
        f"  ⏳ Awaiting approval (ID: {approval.approval_id})"
    )

    logger.info(
        "scheduler_agent_completed",
        email_id=email_data["id"],
        scheduled_at=scheduled_at.isoformat(),
        follow_up_hours=follow_up_hours,
    )
    if span and tracer:
        tracer.end_span(span)
    metrics.increment("follow_ups_proposed")
    metrics.record_latency("scheduling_ms", (time.time() - start_time) * 1000)

    return {
        "follow_up": follow_up.model_dump(mode="json"),
        "pending_approvals": state.get("pending_approvals", []) + [approval.model_dump()],
        "messages": [AIMessage(content=schedule_msg)],
    }


def _determine_follow_up_hours(priority: str, intent: str, memory_context: list[str]) -> int:
    """Determine follow-up timing based on priority and user preferences."""
    # Check if memory context has a default follow-up preference
    default_hours = 24
    for ctx in memory_context:
        if "follow_up_default_hours" in ctx:
            try:
                # Extract the value from the preference string
                parts = ctx.split("=")
                if len(parts) >= 2:
                    default_hours = int(parts[1].strip().split(".")[0])
            except (ValueError, IndexError):
                pass

    # Adjust based on priority
    if priority == "urgent":
        return max(1, default_hours // 8)  # ~3 hours
    elif priority == "high":
        return max(4, default_hours // 4)  # ~6 hours
    elif priority == "low":
        return default_hours * 2  # 48 hours
    else:
        return default_hours


def _build_follow_up_description(email_data: dict, classification: dict) -> str:
    """Build a meaningful follow-up description."""
    intent = classification.get("intent", "")
    summary = classification.get("summary", email_data.get("subject", ""))

    if intent == "question":
        return f"Check if you've answered: {summary}"
    elif intent == "request":
        return f"Follow up on request: {summary}"
    elif intent == "meeting_invite":
        return f"Confirm meeting attendance: {summary}"
    elif intent == "follow_up":
        return f"Review follow-up thread: {summary}"
    else:
        return f"Review and respond: {summary}"

