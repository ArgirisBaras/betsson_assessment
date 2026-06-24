"""Tracing — LangGraph callback handler for span-style tracing.

Records agent transitions, tool calls, and LLM invocations
for debugging and performance analysis.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class TraceRecord:
    """A single trace span."""

    def __init__(self, span_type: str, name: str, metadata: dict | None = None):
        self.span_id = f"span-{int(time.time() * 1000)}"
        self.span_type = span_type  # agent | tool | llm
        self.name = name
        self.start_time = datetime.now(timezone.utc)
        self.end_time: datetime | None = None
        self.duration_ms: float = 0
        self.metadata = metadata or {}
        self.status = "running"
        self.error: str | None = None

    def finish(self, status: str = "success", error: str | None = None):
        self.end_time = datetime.now(timezone.utc)
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.status = status
        self.error = error

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "span_type": self.span_type,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error": self.error,
            "metadata": self.metadata,
        }


class AgentTracer:
    """Collects trace spans for a single orchestrator run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.spans: list[TraceRecord] = []
        self.start_time = datetime.now(timezone.utc)

    def start_span(self, span_type: str, name: str, **metadata) -> TraceRecord:
        span = TraceRecord(span_type, name, metadata)
        self.spans.append(span)
        logger.debug(
            "trace_span_started",
            run_id=self.run_id,
            span_id=span.span_id,
            span_type=span_type,
            name=name,
        )
        return span

    def end_span(self, span: TraceRecord, status: str = "success", error: str | None = None):
        span.finish(status, error)
        logger.debug(
            "trace_span_ended",
            run_id=self.run_id,
            span_id=span.span_id,
            duration_ms=span.duration_ms,
            status=status,
        )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "start_time": self.start_time.isoformat(),
            "total_spans": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
        }


# ── Global trace store (in-memory for demo) ─────────────────────────────────

_traces: dict[str, AgentTracer] = {}


def create_tracer(run_id: str) -> AgentTracer:
    """Create and register a new tracer for a processing run."""
    tracer = AgentTracer(run_id)
    _traces[run_id] = tracer
    return tracer


def get_tracer(run_id: str) -> AgentTracer | None:
    """Retrieve a tracer by run ID."""
    return _traces.get(run_id)


def get_latest_tracer() -> AgentTracer | None:
    """Return the most recently created tracer (current processing run)."""
    if _traces:
        return list(_traces.values())[-1]
    return None


def get_all_traces() -> list[dict]:
    """Return all traces as dicts."""
    return [t.to_dict() for t in _traces.values()]


def clear_traces() -> None:
    """Clear all stored traces."""
    _traces.clear()

