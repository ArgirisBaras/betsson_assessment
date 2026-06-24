"""FastAPI application entry point.

Sets up the app with CORS, middleware, lifespan events,
and all API route modules.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api import approvals, inbox, memory_routes
from app.api.ui import router as ui_router
from app.memory.loader import seed_all
from app.observability.logging import CorrelationIdMiddleware, setup_logging
from app.observability.metrics import metrics
from app.observability.tracing import get_all_traces


# ── Lifespan: startup / shutdown ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — seed data on startup, cleanup on shutdown."""
    setup_logging()
    logger = structlog.get_logger(__name__)
    logger.info("application_starting")

    # Seed demo data (non-fatal if it fails)
    try:
        seed_all()
    except Exception as exc:
        logger.warning("seed_data_failed_on_startup", error=str(exc))
    logger.info("application_ready")

    yield

    logger.info("application_shutting_down")


# ── App creation ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Email Assistant — Intelligent Agent-based Email Management",
    description=(
        "An agentic email assistant that reads, classifies, summarizes, "
        "drafts replies, and schedules follow-ups with human-in-the-loop approval."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)

# Routes
app.include_router(inbox.router)
app.include_router(approvals.router)
app.include_router(memory_routes.router)
app.include_router(ui_router)


# ── Root & utility endpoints ─────────────────────────────────────────────────

def _health_payload() -> dict:
    """Return service health/status information."""
    return {
        "service": "email-assistant",
        "status": "healthy",
        "version": "0.1.0",
    }

@app.get("/", tags=["health"])
async def root(request: Request):
    """Health check endpoint.

    Browser requests are redirected to the web UI so Docker Desktop's
    published-port link opens the demo directly. Non-browser/API requests
    still receive JSON for health checks and tests.
    """
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url="/ui")

    return _health_payload()


@app.get("/health", tags=["health"])
async def health():
    """Dedicated JSON health/status endpoint."""
    return _health_payload()


@app.get("/metrics", tags=["observability"])
async def get_metrics():
    """Get current metrics snapshot."""
    return metrics.get_snapshot()


@app.get("/traces", tags=["observability"])
async def get_traces():
    """Get all processing traces."""
    traces = get_all_traces()
    return {"total": len(traces), "traces": traces}


@app.post("/reset", tags=["admin"])
async def reset_system():
    """Reset the system — re-seed data, clear metrics and traces."""
    from app.observability.tracing import clear_traces
    from app.tools.calendar_api import reset_calendar

    seed_all()
    metrics.reset()
    clear_traces()
    reset_calendar()
    approvals._approvals.clear()

    return {"status": "reset_complete"}

