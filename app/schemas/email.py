"""Email-related schemas — structured I/O contract for all email data."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EmailPriority(str, Enum):
    """Priority levels for incoming emails."""
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class EmailLabel(str, Enum):
    """Standard labels that can be applied to emails."""
    INBOX = "inbox"
    ACTION_REQUIRED = "action_required"
    FOLLOW_UP = "follow_up"
    FYI = "fyi"
    MEETING = "meeting"
    SPAM = "spam"
    ARCHIVED = "archived"


class EmailIntent(str, Enum):
    """Classified intent of an email message."""
    QUESTION = "question"
    REQUEST = "request"
    INFORMATION = "information"
    MEETING_INVITE = "meeting_invite"
    FOLLOW_UP = "follow_up"
    COMPLAINT = "complaint"
    FEEDBACK = "feedback"
    SPAM = "spam"


class EmailMessage(BaseModel):
    """A single email message."""
    id: str = Field(description="Unique message identifier")
    thread_id: str = Field(description="Thread/conversation identifier")
    from_address: str = Field(description="Sender email address")
    to_addresses: list[str] = Field(description="Recipient email addresses")
    cc_addresses: list[str] = Field(default_factory=list, description="CC recipients")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Email body text")
    timestamp: datetime = Field(description="When the email was sent")
    labels: list[EmailLabel] = Field(default_factory=lambda: [EmailLabel.INBOX])
    is_read: bool = Field(default=False)
    attachments: list[str] = Field(default_factory=list, description="Attachment filenames")


class EmailThread(BaseModel):
    """A conversation thread containing multiple messages."""
    thread_id: str = Field(description="Thread identifier")
    subject: str = Field(description="Thread subject")
    messages: list[EmailMessage] = Field(description="Messages in chronological order")
    participant_addresses: list[str] = Field(description="All participants in thread")


class ClassifiedEmail(BaseModel):
    """An email after classification with intent and priority."""
    email: EmailMessage = Field(description="The original email")
    intent: EmailIntent = Field(description="Classified intent")
    priority: EmailPriority = Field(description="Assigned priority")
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence")
    suggested_labels: list[EmailLabel] = Field(description="Suggested labels")
    summary: str = Field(default="", description="Brief one-line summary")


class ThreadSummary(BaseModel):
    """Summary of an email thread."""
    thread_id: str
    subject: str
    summary: str = Field(description="Concise summary of the thread")
    key_points: list[str] = Field(description="Bullet-point key takeaways")
    action_items: list[str] = Field(description="Action items extracted")
    participants: list[str] = Field(description="Participants involved")
    sentiment: str = Field(default="neutral", description="Overall sentiment")

