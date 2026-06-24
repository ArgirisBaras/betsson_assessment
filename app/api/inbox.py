"""Inbox API routes — read and process emails."""

from __future__ import annotations

import time
import uuid

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.orchestrator import process_email
from app.api.approvals import register_approvals
from app.observability.metrics import metrics
from app.observability.tracing import create_tracer
from app.schemas.email import EmailLabel
from app.tools import mail_api

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/inbox", tags=["inbox"])


class ProcessRequest(BaseModel):
    """Request to process a specific email."""
    email_id: str = Field(description="ID of the email to process")


class ProcessResponse(BaseModel):
    """Response from email processing."""
    email_id: str
    status: str
    classification: dict | None = None
    thread_summary: dict | None = None
    draft_reply: dict | None = None
    follow_up: dict | None = None
    pending_approvals: list[dict] = []
    processing_messages: list[str] = []
    errors: list[str] = []


@router.get("/")
async def list_inbox(
    unread_only: bool = False,
    label: EmailLabel | None = None,
    limit: int = 50,
):
    """List emails in the inbox with optional filters."""
    emails = mail_api.fetch_inbox(unread_only=unread_only, label=label, limit=limit)
    return {
        "total": len(emails),
        "emails": [e.model_dump() for e in emails],
    }


@router.get("/{email_id}")
async def get_email(email_id: str):
    """Get a specific email by ID."""
    email = mail_api.get_email(email_id)
    if not email:
        raise HTTPException(status_code=404, detail=f"Email {email_id} not found")
    return email.model_dump()


@router.get("/thread/{thread_id}")
async def get_thread(thread_id: str):
    """Get all emails in a thread."""
    messages = mail_api.get_thread(thread_id)
    if not messages:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return {
        "thread_id": thread_id,
        "message_count": len(messages),
        "messages": [m.model_dump() for m in messages],
    }


@router.post("/process", response_model=ProcessResponse)
async def process_email_endpoint(request: ProcessRequest):
    """Process an email through the agent orchestrator pipeline.

    This triggers the full flow: read → classify → route → {summarize, draft, schedule}.
    Any outgoing actions will require approval via the /approvals endpoints.
    """
    email = mail_api.get_email(request.email_id)
    if not email:
        raise HTTPException(status_code=404, detail=f"Email {request.email_id} not found")

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    tracer = create_tracer(run_id)

    # Track metrics
    start_time = time.time()
    metrics.increment("emails_processed")

    span = tracer.start_span("orchestrator", "process_email", email_id=request.email_id)

    try:
        result = await process_email(
            email_data=email.model_dump(),
            thread_id=f"process-{request.email_id}-{run_id}",
            run_id=run_id,
        )

        tracer.end_span(span)
        duration_ms = (time.time() - start_time) * 1000
        metrics.record_latency("total_processing_ms", duration_ms)

        # Extract message content for response
        processing_messages = []
        for msg in result.get("messages", []):
            if hasattr(msg, "content"):
                processing_messages.append(msg.content)

        # Register pending approvals in the approval store for HITL flow
        pending = result.get("pending_approvals", [])
        if pending:
            register_approvals(pending)

        return ProcessResponse(
            email_id=request.email_id,
            status="completed",
            classification=result.get("classification"),
            thread_summary=result.get("thread_summary"),
            draft_reply=result.get("draft_reply"),
            follow_up=result.get("follow_up"),
            pending_approvals=result.get("pending_approvals", []),
            processing_messages=processing_messages,
            errors=result.get("errors", []),
        )

    except Exception as exc:
        tracer.end_span(span, status="error", error=str(exc))
        metrics.increment("errors_total")
        logger.error("email_processing_failed", email_id=request.email_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(exc)}")

