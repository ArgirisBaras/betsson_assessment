"""Memory API routes — CRUD for long-term memory (preferences, contacts, org facts)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException

from app.memory.long_term import (
    recall_contacts,
    recall_org_facts,
    recall_preferences,
    store_contact,
    store_org_fact,
    store_preference,
)
from app.schemas.memory import ContactInfo, OrgFact, UserPreference
from app.tools import knowledge_store as ks

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/memory", tags=["memory"])


# ── Preferences ──────────────────────────────────────────────────────────────

@router.get("/preferences")
async def list_preferences():
    """List all stored user preferences."""
    docs = ks.get_all_documents(ks.PREFERENCES)
    return {"total": len(docs), "preferences": docs}


@router.post("/preferences")
async def add_preference(pref: UserPreference):
    """Add or update a user preference."""
    store_preference(pref)
    return {"status": "stored", "key": pref.key}


@router.get("/preferences/search")
async def search_preferences(q: str, n: int = 5):
    """Semantic search over preferences."""
    results = recall_preferences(q, n=n)
    return {"query": q, "results": results}


# ── Contacts ────────────────────────────────────────────────────────────────

@router.get("/contacts")
async def list_contacts():
    """List all stored contacts."""
    docs = ks.get_all_documents(ks.CONTACTS)
    return {"total": len(docs), "contacts": docs}


@router.post("/contacts")
async def add_contact(contact: ContactInfo):
    """Add or update a contact."""
    store_contact(contact)
    return {"status": "stored", "email": contact.email}


@router.get("/contacts/search")
async def search_contacts(q: str, n: int = 5):
    """Semantic search over contacts."""
    results = recall_contacts(q, n=n)
    return {"query": q, "results": results}


# ── Org Facts ───────────────────────────────────────────────────────────────

@router.get("/org-facts")
async def list_org_facts():
    """List all stored organizational facts."""
    docs = ks.get_all_documents(ks.ORG_FACTS)
    return {"total": len(docs), "org_facts": docs}


@router.post("/org-facts")
async def add_org_fact(fact: OrgFact):
    """Add or update an organizational fact."""
    store_org_fact(fact)
    return {"status": "stored", "fact_id": fact.fact_id}


@router.get("/org-facts/search")
async def search_org_facts(q: str, n: int = 5):
    """Semantic search over organizational facts."""
    results = recall_org_facts(q, n=n)
    return {"query": q, "results": results}

