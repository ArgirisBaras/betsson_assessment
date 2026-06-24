"""Reader agent — reads, classifies, and labels incoming emails.

This is the entry-point worker in the orchestrator graph.
It fetches the email, retrieves relevant memory context,
classifies intent/priority, and applies labels.
"""

from __future__ import annotations

import time

import structlog
from langchain_core.messages import AIMessage

from app.memory.long_term import get_memory_context
from app.observability.metrics import metrics
from app.observability.tracing import get_latest_tracer
from app.schemas.email import EmailMessage
from app.tools import mail_api
from app.tools.classifier import classify_email

logger = structlog.get_logger(__name__)


async def reader_node(state: dict) -> dict:
    """LangGraph node: read and classify the current email.

    Expects state['current_email'] to contain an EmailMessage dict.
    Produces state updates: classification, memory_context, next_action.
    """
    logger.info("reader_agent_started")
    tracer = get_latest_tracer()
    span = tracer.start_span("agent", "reader", email_id=state.get("current_email", {}).get("id")) if tracer else None

    email_data = state.get("current_email")
    if not email_data:
        return {
            "errors": state.get("errors", []) + ["No email provided to reader agent"],
            "next_action": "end",
            "messages": [AIMessage(content="Error: No email to process.")],
        }

    # Reconstruct EmailMessage from dict
    email = EmailMessage(**email_data)

    # Mark as read
    mail_api.mark_as_read(email.id)

    # Retrieve long-term memory context
    memory_items = get_memory_context(
        email_subject=email.subject,
        email_body=email.body,
        sender=email.from_address,
    )

    # Classify the email
    memory_context_str = "\n".join(memory_items) if memory_items else "No context available."
    classification_start = time.time()
    classified = await classify_email(email, memory_context=memory_context_str)
    metrics.increment("emails_classified")
    metrics.increment(f"classified_intent_{classified.intent.value}")
    metrics.increment(f"classified_priority_{classified.priority.value}")
    metrics.record_latency("classification_ms", (time.time() - classification_start) * 1000)

    # Apply suggested labels
    for label in classified.suggested_labels:
        mail_api.apply_label(email.id, label)

    # Determine next action based on classification
    next_action = _route_email(classified.intent.value, classified.priority.value)

    summary_msg = (
        f"📧 Email classified:\n"
        f"  From: {email.from_address}\n"
        f"  Subject: {email.subject}\n"
        f"  Intent: {classified.intent.value}\n"
        f"  Priority: {classified.priority.value}\n"
        f"  Summary: {classified.summary}\n"
        f"  → Next action: {next_action}"
    )

    logger.info(
        "reader_agent_completed",
        email_id=email.id,
        intent=classified.intent.value,
        priority=classified.priority.value,
        next_action=next_action,
    )
    if span and tracer:
        tracer.end_span(span)

    return {
        "classification": classified.model_dump(),
        "memory_context": memory_items,
        "next_action": next_action,
        "messages": [AIMessage(content=summary_msg)],
    }


def _route_email(intent: str, priority: str) -> str:
    """Determine routing based on intent and priority.

    Returns one of: 'summarize', 'draft', 'schedule', 'summarize_and_draft', 'end'
    """
    # Urgent/high priority with actionable intent → draft a reply
    if priority in ("urgent", "high") and intent in ("request", "question", "complaint"):
        return "draft"

    # Meeting invites → schedule
    if intent == "meeting_invite":
        return "schedule"

    # Follow-up emails → schedule a reminder
    if intent == "follow_up":
        return "schedule"

    # Questions → draft a reply
    if intent == "question":
        return "draft"

    # Requests → summarize then draft
    if intent == "request":
        return "summarize_and_draft"

    # Information/FYI → just summarize
    if intent in ("information", "feedback"):
        return "summarize"

    # Spam → end
    if intent == "spam":
        return "end"

    return "summarize"

