"""Central LLM provider abstraction.

Keeps model construction and enable/disable policy in one place so agents do not
instantiate provider-specific clients directly. This makes the assistant easier to
mock in tests and easier to migrate to another LLM backend later.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_openai import ChatOpenAI

from app.config import settings

logger = structlog.get_logger(__name__)


class LLMDisabledError(RuntimeError):
    """Raised when an LLM call is requested while chat LLMs are disabled."""


def is_llm_enabled() -> bool:
    """Return whether chat LLM calls should be attempted.

    An API key is still required because the current backend is OpenAI. Test/demo
    placeholders such as ``sk-test`` and ``sk-your-key-here`` are treated as
    disabled to avoid slow failed network calls while preserving deterministic
    fallback behavior.
    """
    api_key = settings.openai_api_key.strip()
    return (
        settings.llm_enabled
        and bool(api_key)
        and api_key not in {"sk-test", "sk-your-key-here"}
    )


def create_chat_model(*, temperature: float = 0.0, **overrides: Any) -> ChatOpenAI:
    """Create the configured chat model.

    Raises:
        LLMDisabledError: if chat LLM calls are disabled or no usable API key is
            configured. Callers should catch this and use their deterministic
            fallback path.
    """
    if not is_llm_enabled():
        raise LLMDisabledError("Chat LLM is disabled or no usable OpenAI API key is configured")

    model_kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "api_key": settings.openai_api_key,
        "temperature": temperature,
    }
    model_kwargs.update(overrides)
    logger.debug("chat_model_created", model=settings.openai_model, temperature=temperature)
    return ChatOpenAI(**model_kwargs)

