"""Drafter agent — generates contextual email reply drafts.

Creates draft replies based on classification, thread context,
and long-term memory. All drafts go through the HITL approval flow.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import structlog
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import settings
from app.observability.metrics import metrics
from app.observability.tracing import get_tracer
from app.schemas.actions import ActionType, ApprovalRequest, DraftReply

logger = structlog.get_logger(__name__)


class DraftOutput(BaseModel):
    """LLM structured output for reply drafting."""
    body: str = Field(description="The email reply body text")
    tone: str = Field(description="Tone used: formal, friendly, urgent, etc.")
    reasoning: str = Field(description="Brief reasoning for the draft approach")


DRAFT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert email reply drafter for a Senior AI Engineer at a sportsbook company. "
        "Write professional, concise replies that address all points raised in the email. "
        "Match the appropriate tone based on the context and relationship.\n\n"
        "User preferences and context:\n{memory_context}\n\n"
        "Classification:\n{classification}",
    ),
    (
        "human",
        "Draft a reply to this email:\n\n"
        "From: {from_address}\n"
        "Subject: {subject}\n"
        "Body:\n{body}\n\n"
        "Thread summary (if available):\n{thread_summary}",
    ),
])


async def drafter_node(state: dict) -> dict:
    """LangGraph node: draft a reply to the current email.

    Generates a draft and creates an ApprovalRequest for HITL review.
    """
    logger.info("drafter_agent_started")
    tracer = get_tracer(state.get("run_id", ""))
    span = tracer.start_span("agent", "drafter") if tracer else None

    email_data = state.get("current_email")
    if not email_data:
        return {
            "errors": state.get("errors", []) + ["No email for drafting"],
            "messages": [AIMessage(content="Error: No email to draft reply for.")],
        }

    classification = state.get("classification", {})
    thread_summary = state.get("thread_summary")
    memory_context = "\n".join(state.get("memory_context", [])) or "No context."

    thread_summary_str = ""
    if thread_summary:
        thread_summary_str = (
            f"Summary: {thread_summary.get('summary', '')}\n"
            f"Key points: {', '.join(thread_summary.get('key_points', []))}\n"
            f"Action items: {', '.join(thread_summary.get('action_items', []))}"
        )
    start_time = time.time()

    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        structured_llm = llm.with_structured_output(DraftOutput)

        draft_output: DraftOutput = await structured_llm.ainvoke(
            DRAFT_PROMPT.format_messages(
                from_address=email_data["from_address"],
                subject=email_data["subject"],
                body=email_data["body"],
                memory_context=memory_context,
                classification=str(classification),
                thread_summary=thread_summary_str or "No thread summary available.",
            )
        )

        draft_body = draft_output.body
        tone = draft_output.tone
        reasoning = draft_output.reasoning
        metrics.increment("llm_calls")

    except Exception as exc:
        logger.warning("drafter_llm_failed", error=str(exc))
        metrics.increment("llm_fallbacks")
        draft_body = (
            f"Hi {email_data['from_address'].split('@')[0].replace('.', ' ').title()},\n\n"
            f"Thank you for your email regarding \"{email_data['subject']}\".\n"
            f"I've reviewed your message and will get back to you with a detailed response shortly.\n\n"
            f"Best regards"
        )
        tone = "professional"
        reasoning = "Fallback template used due to LLM unavailability"

    # Create the draft reply
    draft = DraftReply(
        email_id=email_data["id"],
        thread_id=email_data["thread_id"],
        to_addresses=[email_data["from_address"]],
        cc_addresses=email_data.get("cc_addresses", []),
        subject=f"Re: {email_data['subject']}",
        body=draft_body,
        tone=tone,
        reasoning=reasoning,
    )

    # Create approval request (HITL)
    approval = ApprovalRequest(
        approval_id=f"apr-{uuid.uuid4().hex[:8]}",
        action_type=ActionType.SEND_REPLY,
        description=f"Send reply to {email_data['from_address']} re: {email_data['subject']}",
        payload=draft.model_dump(),
        email_id=email_data["id"],
        thread_id=email_data["thread_id"],
        created_at=datetime.now(timezone.utc),
    )

    draft_msg = (
        f"✉️ Draft Reply Prepared:\n"
        f"  To: {', '.join(draft.to_addresses)}\n"
        f"  Subject: {draft.subject}\n"
        f"  Tone: {tone}\n"
        f"  Reasoning: {reasoning}\n"
        f"  ⏳ Awaiting approval (ID: {approval.approval_id})"
    )

    logger.info(
        "drafter_agent_completed",
        email_id=email_data["id"],
        approval_id=approval.approval_id,
        tone=tone,
    )
    if span and tracer:
        tracer.end_span(span)
    metrics.increment("drafts_generated")
    metrics.record_latency("drafting_ms", (time.time() - start_time) * 1000)

    return {
        "draft_reply": draft.model_dump(),
        "pending_approvals": state.get("pending_approvals", []) + [approval.model_dump()],
        "messages": [AIMessage(content=draft_msg)],
    }

