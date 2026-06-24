"""Structured logging configuration using structlog.

Provides JSON-formatted logs with correlation IDs, timestamps,
and contextual metadata for full observability.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

import logging

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

# Correlation ID for request tracing
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def add_correlation_id(logger, method_name, event_dict):
    """Structlog processor: inject correlation ID into every log entry."""
    cid = correlation_id_var.get("")
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def setup_logging() -> None:
    """Configure structlog with JSON output and processors."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            add_correlation_id,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that assigns a correlation ID to each request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get("X-Correlation-ID", uuid.uuid4().hex[:12])
        correlation_id_var.set(cid)

        logger = structlog.get_logger()
        logger.info(
            "request_started",
            method=request.method,
            path=str(request.url.path),
            correlation_id=cid,
        )

        response = await call_next(request)

        logger.info(
            "request_completed",
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            correlation_id=cid,
        )

        response.headers["X-Correlation-ID"] = cid
        return response

