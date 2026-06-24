"""Seed data loader — populates long-term memory and inbox for demos."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from app.memory.long_term import store_contact, store_org_fact, store_preference
from app.schemas.memory import ContactInfo, OrgFact, UserPreference
from app.tools.knowledge_store import reset_store
from app.tools.mail_api import reset_inbox

logger = structlog.get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_seed_contacts() -> None:
    """Load sample contacts into ChromaDB."""
    path = DATA_DIR / "sample_contacts.json"
    if not path.exists():
        logger.warning("sample_contacts.json not found")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data.get("contacts", []):
        store_contact(ContactInfo(**item))

    for item in data.get("preferences", []):
        store_preference(UserPreference(**item))

    for item in data.get("org_facts", []):
        store_org_fact(OrgFact(**item))

    logger.info(
        "seed_data_loaded",
        contacts=len(data.get("contacts", [])),
        preferences=len(data.get("preferences", [])),
        org_facts=len(data.get("org_facts", [])),
    )


def seed_all() -> None:
    """Load all seed data — inbox + long-term memory."""
    reset_inbox()
    reset_store()
    try:
        load_seed_contacts()
    except Exception as exc:
        logger.warning("seed_contacts_failed", error=str(exc))
    logger.info("all_seed_data_loaded")

