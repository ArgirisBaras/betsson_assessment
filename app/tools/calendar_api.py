"""Mock Calendar / Task API — simulates calendar and reminder services."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class CalendarEvent(BaseModel):
    """A calendar event or reminder."""
    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:8]}")
    title: str
    description: str = ""
    scheduled_at: datetime
    duration_minutes: int = 30
    attendees: list[str] = Field(default_factory=list)
    event_type: str = "reminder"  # reminder | meeting | follow_up
    related_email_id: str = ""
    related_thread_id: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── In-memory store ──────────────────────────────────────────────────────────

_events: dict[str, CalendarEvent] = {}


def create_event(
    title: str,
    scheduled_at: datetime,
    description: str = "",
    duration_minutes: int = 30,
    attendees: list[str] | None = None,
    event_type: str = "reminder",
    related_email_id: str = "",
    related_thread_id: str = "",
) -> CalendarEvent:
    """Create a calendar event or reminder."""
    event = CalendarEvent(
        title=title,
        description=description,
        scheduled_at=scheduled_at,
        duration_minutes=duration_minutes,
        attendees=attendees or [],
        event_type=event_type,
        related_email_id=related_email_id,
        related_thread_id=related_thread_id,
    )
    _events[event.event_id] = event
    logger.info(
        "calendar_event_created",
        event_id=event.event_id,
        title=title,
        scheduled_at=scheduled_at.isoformat(),
        event_type=event_type,
    )
    return event


def list_events(
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    event_type: Optional[str] = None,
) -> list[CalendarEvent]:
    """List calendar events with optional filters."""
    events = list(_events.values())
    if from_date:
        events = [e for e in events if e.scheduled_at >= from_date]
    if to_date:
        events = [e for e in events if e.scheduled_at <= to_date]
    if event_type:
        events = [e for e in events if e.event_type == event_type]
    events.sort(key=lambda e: e.scheduled_at)
    return events


def get_event(event_id: str) -> Optional[CalendarEvent]:
    """Get a single event by ID."""
    return _events.get(event_id)


def delete_event(event_id: str) -> bool:
    """Delete a calendar event."""
    if event_id in _events:
        del _events[event_id]
        logger.info("calendar_event_deleted", event_id=event_id)
        return True
    return False


def reset_calendar() -> None:
    """Clear all events (for tests / demo resets)."""
    _events.clear()

