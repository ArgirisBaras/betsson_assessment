"""Summarizer agent — generates concise summaries of email threads.

Produces structured ThreadSummary with key points, action items, and sentiment.
"""

from __future__ import annotations

import time

import structlog
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from app.config import settings
from app.observability.metrics import metrics
from app.observability.tracing import get_latest_tracer
from app.schemas.email import EmailMessage, ThreadSummary
from app.tools import mail_api

logger = structlog.get_logger(__name__)


SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert email summarizer. Create concise, actionable summaries "
        "of email threads. Focus on key decisions, action items, and deadlines.\n\n"
        "Additional context:\n{memory_context}",
    ),
    (
        "human",
        "Summarize the following email thread:\n\n{thread_content}",
    ),
])


class SummaryOutput(ThreadSummary):
    """LLM structured output for thread summarization."""
    pass


async def summarizer_node(state: dict) -> dict:
    """LangGraph node: summarize the email thread.

    Reads the thread from the current email's thread_id,
    generates a structured summary, and updates state.
    """
    logger.info("summarizer_agent_started")
    tracer = get_latest_tracer()
    span = tracer.start_span("agent", "summarizer") if tracer else None

    email_data = state.get("current_email")
    if not email_data:
        return {
            "errors": state.get("errors", []) + ["No email for summarization"],
            "messages": [AIMessage(content="Error: No email to summarize.")],
        }

    thread_id = email_data["thread_id"]
    thread_messages = mail_api.get_thread(thread_id)

    if not thread_messages:
        thread_messages = [EmailMessage(**email_data)]

    # Build thread content for the LLM
    thread_content = _format_thread(thread_messages)
    memory_context = "\n".join(state.get("memory_context", [])) or "No context."
    start_time = time.time()

    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.0,
        )
        structured_llm = llm.with_structured_output(SummaryOutput)

        summary: SummaryOutput = await structured_llm.ainvoke(
            SUMMARIZE_PROMPT.format_messages(
                thread_content=thread_content,
                memory_context=memory_context,
            )
        )
        metrics.increment("llm_calls")
    except Exception as exc:
        logger.warning("summarizer_llm_failed", error=str(exc))
        metrics.increment("llm_fallbacks")
        summary = ThreadSummary(
            thread_id=thread_id,
            subject=email_data.get("subject", ""),
            summary=f"Thread with {len(thread_messages)} message(s) about: {email_data.get('subject', '')}",
            key_points=[email_data.get("subject", "")],
            action_items=[],
            participants=list({m.from_address for m in thread_messages}),
            sentiment="neutral",
        )

    summary_msg = (
        f"📝 Thread Summary ({thread_id}):\n"
        f"  {summary.summary}\n"
        f"  Key points: {', '.join(summary.key_points[:3])}\n"
        f"  Action items: {len(summary.action_items)}"
    )

    logger.info("summarizer_agent_completed", thread_id=thread_id)
    if span and tracer:
        tracer.end_span(span)
    metrics.increment("summaries_generated")
    metrics.record_latency("summarization_ms", (time.time() - start_time) * 1000)

    return {
        "thread_summary": summary.model_dump(),
        "messages": [AIMessage(content=summary_msg)],
    }


def _format_thread(messages: list[EmailMessage]) -> str:
    """Format a list of emails into a readable thread for the LLM."""
    parts = []
    for msg in messages:
        parts.append(
            f"--- Message from {msg.from_address} ({msg.timestamp.isoformat()}) ---\n"
            f"Subject: {msg.subject}\n\n"
            f"{msg.body}\n"
        )
    return "\n".join(parts)

