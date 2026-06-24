"""Action schemas — drafts, follow-ups, and human-in-the-loop approvals."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of outgoing actions that require approval."""
    SEND_REPLY = "send_reply"
    APPLY_LABEL = "apply_label"
    SCHEDULE_FOLLOWUP = "schedule_followup"
    CREATE_REMINDER = "create_reminder"
    ARCHIVE = "archive"


class ApprovalStatus(str, Enum):
    """Status of a pending approval."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


class DraftReply(BaseModel):
    """A drafted email reply awaiting approval."""
    email_id: str = Field(description="Original email being replied to")
    thread_id: str = Field(description="Thread identifier")
    to_addresses: list[str] = Field(description="Recipients")
    cc_addresses: list[str] = Field(default_factory=list)
    subject: str = Field(description="Reply subject")
    body: str = Field(description="Draft reply body")
    tone: str = Field(default="professional", description="Tone used in drafting")
    reasoning: str = Field(default="", description="Why this reply was drafted")


class FollowUp(BaseModel):
    """A scheduled follow-up or reminder."""
    email_id: str = Field(description="Related email")
    thread_id: str = Field(description="Related thread")
    scheduled_at: datetime = Field(description="When to follow up")
    description: str = Field(description="What to follow up on")
    assignee: str = Field(default="user", description="Who should follow up")


class ApprovalRequest(BaseModel):
    """A request for human approval before executing an action."""
    approval_id: str = Field(description="Unique approval request ID")
    action_type: ActionType = Field(description="Type of action")
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    description: str = Field(description="Human-readable description of the action")
    payload: dict = Field(description="Action-specific data (DraftReply, FollowUp, etc.)")
    email_id: str = Field(default="", description="Related email ID")
    thread_id: str = Field(default="", description="Related thread ID")


class ApprovalResponse(BaseModel):
    """Human response to an approval request."""
    approval_id: str = Field(description="Which approval this responds to")
    decision: ApprovalStatus = Field(description="Approve, reject, or edit")
    edited_payload: Optional[dict] = Field(
        default=None, description="Modified payload if decision is 'edited'"
    )
    feedback: str = Field(default="", description="Optional feedback from user")

