"""Metrics — in-memory counters and gauges for observability.

Tracks key operational metrics like emails processed, approval rates,
agent latencies, and error counts. Exposed via GET /metrics.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_lock = Lock()


class MetricsCollector:
    """Thread-safe in-memory metrics collector."""

    def __init__(self):
        self._counters: dict[str, int] = {
            "emails_processed": 0,
            "emails_classified": 0,
            "drafts_generated": 0,
            "drafts_approved": 0,
            "drafts_rejected": 0,
            "drafts_edited": 0,
            "approvals_approved": 0,
            "approvals_rejected": 0,
            "approvals_edited": 0,
            "send_replies_approved": 0,
            "send_replies_rejected": 0,
            "send_replies_edited": 0,
            "follow_ups_approved": 0,
            "follow_ups_rejected": 0,
            "follow_ups_edited": 0,
            "follow_ups_scheduled": 0,
            "summaries_generated": 0,
            "errors_total": 0,
            "llm_calls": 0,
            "llm_fallbacks": 0,
        }
        self._latencies: dict[str, list[float]] = {
            "classification_ms": [],
            "summarization_ms": [],
            "drafting_ms": [],
            "scheduling_ms": [],
            "total_processing_ms": [],
        }
        self._started_at = datetime.now(timezone.utc)

    def increment(self, counter: str, value: int = 1) -> None:
        """Increment a counter."""
        with _lock:
            self._counters[counter] = self._counters.get(counter, 0) + value

    def record_latency(self, metric: str, duration_ms: float) -> None:
        """Record a latency measurement."""
        with _lock:
            if metric not in self._latencies:
                self._latencies[metric] = []
            self._latencies[metric].append(duration_ms)

    def get_snapshot(self) -> dict[str, Any]:
        """Return a snapshot of all metrics."""
        with _lock:
            latency_stats = {}
            for name, values in self._latencies.items():
                if values:
                    latency_stats[name] = {
                        "count": len(values),
                        "avg_ms": round(sum(values) / len(values), 2),
                        "min_ms": round(min(values), 2),
                        "max_ms": round(max(values), 2),
                        "p50_ms": round(sorted(values)[len(values) // 2], 2),
                    }
                else:
                    latency_stats[name] = {"count": 0}

            return {
                "counters": dict(self._counters),
                "latencies": latency_stats,
                "uptime_seconds": (datetime.now(timezone.utc) - self._started_at).total_seconds(),
                "snapshot_at": datetime.now(timezone.utc).isoformat(),
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with _lock:
            for key in self._counters:
                self._counters[key] = 0
            for key in self._latencies:
                self._latencies[key] = []
            self._started_at = datetime.now(timezone.utc)


# ── Singleton instance ───────────────────────────────────────────────────────

metrics = MetricsCollector()

