"""Mock Mail API adapter — simulates an email service (Gmail/Outlook-like).

Provides an in-memory inbox that agents can read from, label, and send through.
In production this would be replaced with a real IMAP/Graph API client.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import structlog

from app.schemas.email import EmailLabel, EmailMessage

logger = structlog.get_logger(__name__)

# ── In-memory store ──────────────────────────────────────────────────────────

_inbox: dict[str, EmailMessage] = {}
_sent: list[EmailMessage] = []


def _seed_inbox() -> None:
    """Load sample emails from data/sample_emails.json into memory."""
    sample_path = Path(__file__).resolve().parents[2] / "data" / "sample_emails.json"
    if not sample_path.exists():
        logger.warning("sample_emails.json not found — inbox will be empty", path=str(sample_path))
        return
    with open(sample_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    for item in raw:
        item["timestamp"] = datetime.fromisoformat(item["timestamp"])
        item["labels"] = [EmailLabel(l) for l in item.get("labels", ["inbox"])]
        email = EmailMessage(**item)
        _inbox[email.id] = email
    logger.info("inbox_seeded", count=len(_inbox))


def reset_inbox() -> None:
    """Clear and re-seed the inbox (useful for tests / demo resets)."""
    _inbox.clear()
    _sent.clear()
    _seed_inbox()


# ── Public API ───────────────────────────────────────────────────────────────

def fetch_inbox(
    unread_only: bool = False,
    label: Optional[EmailLabel] = None,
    limit: int = 50,
) -> list[EmailMessage]:
    """Fetch emails from the inbox with optional filters."""
    emails = list(_inbox.values())
    if unread_only:
        emails = [e for e in emails if not e.is_read]
    if label:
        emails = [e for e in emails if label in e.labels]
    emails.sort(key=lambda e: e.timestamp, reverse=True)
    logger.info("inbox_fetched", total=len(emails), unread_only=unread_only, label=label)
    return emails[:limit]


def get_email(email_id: str) -> Optional[EmailMessage]:
    """Get a single email by ID."""
    return _inbox.get(email_id)


def get_thread(thread_id: str) -> list[EmailMessage]:
    """Get all emails in a thread, sorted chronologically."""
    thread = [e for e in _inbox.values() if e.thread_id == thread_id]
    thread.sort(key=lambda e: e.timestamp)
    return thread


def mark_as_read(email_id: str) -> bool:
    """Mark an email as read."""
    if email_id in _inbox:
        _inbox[email_id].is_read = True
        logger.info("email_marked_read", email_id=email_id)
        return True
    return False


def apply_label(email_id: str, label: EmailLabel) -> bool:
    """Apply a label to an email."""
    if email_id in _inbox:
        if label not in _inbox[email_id].labels:
            _inbox[email_id].labels.append(label)
        logger.info("label_applied", email_id=email_id, label=label.value)
        return True
    return False


def send_email(
    to_addresses: list[str],
    subject: str,
    body: str,
    cc_addresses: list[str] | None = None,
    thread_id: str | None = None,
) -> EmailMessage:
    """Send (mock) an email and return the sent message."""
    sent_msg = EmailMessage(
        id=f"sent-{uuid.uuid4().hex[:8]}",
        thread_id=thread_id or f"thread-{uuid.uuid4().hex[:8]}",
        from_address="user@company.com",
        to_addresses=to_addresses,
        cc_addresses=cc_addresses or [],
        subject=subject,
        body=body,
        timestamp=datetime.now(timezone.utc),
        labels=[],
        is_read=True,
    )
    _sent.append(sent_msg)
    logger.info("email_sent", email_id=sent_msg.id, to=to_addresses, subject=subject)
    return sent_msg


def get_sent_emails() -> list[EmailMessage]:
    """Return all sent emails (for observability / demo)."""
    return list(_sent)


# Seed inbox on module load
_seed_inbox()

