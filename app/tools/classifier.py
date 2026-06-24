"""Email intent classifier and priority ranker.

Uses an LLM to classify email intent and assign priority.
Falls back to a rule-based heuristic if the LLM is unavailable.
"""

from __future__ import annotations

import structlog
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import settings
from app.observability.metrics import metrics
from app.schemas.email import (
    ClassifiedEmail,
    EmailIntent,
    EmailLabel,
    EmailMessage,
    EmailPriority,
)

logger = structlog.get_logger(__name__)


# ── Structured output schema for the LLM ────────────────────────────────────

class ClassificationOutput(BaseModel):
    """LLM output schema for email classification."""
    intent: EmailIntent = Field(description="The primary intent of this email")
    priority: EmailPriority = Field(description="How urgent this email is")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in classification")
    suggested_labels: list[EmailLabel] = Field(description="Labels to apply")
    summary: str = Field(description="One-line summary of the email")
    reasoning: str = Field(description="Brief reasoning for the classification")


CLASSIFICATION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert email classifier. Analyze the email and classify its intent, "
        "priority, and suggest appropriate labels. Be precise and concise.\n\n"
        "Context about the user (if available):\n{memory_context}",
    ),
    (
        "human",
        "Classify this email:\n\n"
        "From: {from_address}\n"
        "To: {to_addresses}\n"
        "Subject: {subject}\n"
        "Date: {timestamp}\n\n"
        "{body}",
    ),
])


async def classify_email(
    email: EmailMessage,
    memory_context: str = "No additional context available.",
) -> ClassifiedEmail:
    """Classify an email using LLM with structured output.

    Returns a ClassifiedEmail with intent, priority, labels, and summary.
    Falls back to rule-based classification if LLM fails.
    """
    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.0,
        )
        structured_llm = llm.with_structured_output(ClassificationOutput)

        result: ClassificationOutput = await structured_llm.ainvoke(
            CLASSIFICATION_PROMPT.format_messages(
                from_address=email.from_address,
                to_addresses=", ".join(email.to_addresses),
                subject=email.subject,
                timestamp=email.timestamp.isoformat(),
                body=email.body,
                memory_context=memory_context,
            )
        )

        classified = ClassifiedEmail(
            email=email,
            intent=result.intent,
            priority=result.priority,
            confidence=result.confidence,
            suggested_labels=result.suggested_labels,
            summary=result.summary,
        )
        metrics.increment("llm_calls")
        logger.info(
            "email_classified",
            email_id=email.id,
            intent=result.intent.value,
            priority=result.priority.value,
            confidence=result.confidence,
        )
        return classified

    except Exception as exc:
        logger.warning("llm_classification_failed", error=str(exc), email_id=email.id)
        metrics.increment("llm_fallbacks")
        return _fallback_classify(email)


def _fallback_classify(email: EmailMessage) -> ClassifiedEmail:
    """Rule-based fallback classifier when LLM is unavailable."""
    subject_lower = email.body.lower() + " " + email.subject.lower()

    # Simple keyword-based rules
    if any(w in subject_lower for w in ["urgent", "asap", "immediately", "critical"]):
        priority = EmailPriority.URGENT
        intent = EmailIntent.REQUEST
        labels = [EmailLabel.ACTION_REQUIRED]
    elif any(w in subject_lower for w in ["meeting", "invite", "calendar", "schedule"]):
        priority = EmailPriority.HIGH
        intent = EmailIntent.MEETING_INVITE
        labels = [EmailLabel.MEETING]
    elif any(w in subject_lower for w in ["follow up", "following up", "check in", "reminder"]):
        priority = EmailPriority.NORMAL
        intent = EmailIntent.FOLLOW_UP
        labels = [EmailLabel.FOLLOW_UP]
    elif "?" in email.subject or any(w in subject_lower for w in ["question", "help", "how to"]):
        priority = EmailPriority.NORMAL
        intent = EmailIntent.QUESTION
        labels = [EmailLabel.ACTION_REQUIRED]
    elif any(w in subject_lower for w in ["fyi", "info", "update", "newsletter"]):
        priority = EmailPriority.LOW
        intent = EmailIntent.INFORMATION
        labels = [EmailLabel.FYI]
    else:
        priority = EmailPriority.NORMAL
        intent = EmailIntent.INFORMATION
        labels = [EmailLabel.INBOX]

    classified = ClassifiedEmail(
        email=email,
        intent=intent,
        priority=priority,
        confidence=0.6,
        suggested_labels=labels,
        summary=f"{intent.value}: {email.subject[:80]}",
    )
    logger.info(
        "email_classified_fallback",
        email_id=email.id,
        intent=intent.value,
        priority=priority.value,
    )
    return classified

