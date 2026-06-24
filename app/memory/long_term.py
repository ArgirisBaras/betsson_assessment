"""Long-term memory — persistent storage for preferences, contacts, and org facts.

Wraps the knowledge_store tool with domain-specific methods for
storing and recalling user preferences, contact information,
and organizational facts. The knowledge store uses a JSON backend for
deterministic demos and can optionally use ChromaDB for vector search.
"""

from __future__ import annotations

import structlog

from app.schemas.memory import ContactInfo, OrgFact, UserPreference
from app.tools import knowledge_store as ks

logger = structlog.get_logger(__name__)


# ── User Preferences ────────────────────────────────────────────────────────

def store_preference(pref: UserPreference) -> None:
    """Persist a user preference."""
    doc = f"User preference: {pref.key} = {pref.value}. {pref.description}"
    ks.add_documents(
        collection_name=ks.PREFERENCES,
        documents=[doc],
        ids=[f"pref-{pref.key}"],
        metadatas=[{"key": pref.key, "value": pref.value}],
    )


def recall_preferences(query: str, n: int = 3) -> list[dict]:
    """Recall relevant user preferences for a given context."""
    return ks.query(ks.PREFERENCES, query, n_results=n)


# ── Contacts ────────────────────────────────────────────────────────────────

def store_contact(contact: ContactInfo) -> None:
    """Persist contact information."""
    doc = (
        f"Contact: {contact.name} ({contact.email}). "
        f"Role: {contact.role}. Organization: {contact.organization}. "
        f"Relationship: {contact.relationship}. Notes: {contact.notes}"
    )
    ks.add_documents(
        collection_name=ks.CONTACTS,
        documents=[doc],
        ids=[f"contact-{contact.email}"],
        metadatas=[{
            "email": contact.email,
            "name": contact.name,
            "organization": contact.organization,
        }],
    )


def recall_contacts(query: str, n: int = 3) -> list[dict]:
    """Find relevant contacts by semantic search."""
    return ks.query(ks.CONTACTS, query, n_results=n)


# ── Organizational Facts ────────────────────────────────────────────────────

def store_org_fact(fact: OrgFact) -> None:
    """Persist an organizational fact."""
    doc = f"[{fact.category}] {fact.content} (source: {fact.source})"
    ks.add_documents(
        collection_name=ks.ORG_FACTS,
        documents=[doc],
        ids=[fact.fact_id],
        metadatas=[{"category": fact.category, "source": fact.source}],
    )


def recall_org_facts(query: str, n: int = 3) -> list[dict]:
    """Recall relevant organizational facts."""
    return ks.query(ks.ORG_FACTS, query, n_results=n)


# ── Unified context retrieval ───────────────────────────────────────────────

def get_memory_context(email_subject: str, email_body: str, sender: str) -> list[str]:
    """Retrieve all relevant long-term memory for processing an email.

    Combines results from preferences, contacts, and org facts
    into a list of context strings for the agent.
    """
    query_text = f"{email_subject} {email_body[:200]} {sender}"
    context_items = []

    # Recall relevant contacts
    contacts = recall_contacts(sender, n=2)
    for c in contacts:
        context_items.append(f"[Contact] {c['document']}")

    # Recall preferences
    prefs = recall_preferences(query_text, n=2)
    for p in prefs:
        context_items.append(f"[Preference] {p['document']}")

    # Recall org facts
    facts = recall_org_facts(query_text, n=3)
    for f in facts:
        context_items.append(f"[OrgFact] {f['document']}")

    logger.info(
        "memory_context_retrieved",
        context_items_count=len(context_items),
        sender=sender,
    )
    return context_items

