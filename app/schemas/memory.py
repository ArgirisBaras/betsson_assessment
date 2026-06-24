"""Memory schemas — user preferences, contacts, and organizational facts."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserPreference(BaseModel):
    """A stored user preference for personalizing assistant behavior."""
    key: str = Field(description="Preference key, e.g. 'reply_tone'")
    value: str = Field(description="Preference value, e.g. 'formal'")
    description: str = Field(default="", description="Human-readable description")
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ContactInfo(BaseModel):
    """Information about a known contact."""
    email: str = Field(description="Contact email address")
    name: str = Field(description="Contact full name")
    role: str = Field(default="", description="Job title or role")
    organization: str = Field(default="", description="Company or organization")
    relationship: str = Field(default="", description="Relationship to user, e.g. 'manager'")
    notes: str = Field(default="", description="Additional notes")
    last_interaction: Optional[datetime] = Field(default=None)


class OrgFact(BaseModel):
    """An organizational fact stored in long-term memory."""
    fact_id: str = Field(description="Unique fact identifier")
    category: str = Field(description="Category: policy, project, team, etc.")
    content: str = Field(description="The fact content")
    source: str = Field(default="", description="Where this fact came from")
    created_at: datetime = Field(default_factory=datetime.utcnow)

