"""Tests for the centralized LLM provider abstraction."""

import pytest

from app.config import settings
from app.llm import provider


def test_llm_disabled_when_flag_is_false(monkeypatch):
    """LLM calls can be disabled centrally for deterministic fallback behavior."""
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(settings, "openai_api_key", "sk-real-looking-key")

    assert provider.is_llm_enabled() is False
    with pytest.raises(provider.LLMDisabledError):
        provider.create_chat_model()


def test_llm_disabled_for_placeholder_keys(monkeypatch):
    """Test/demo placeholder keys should not trigger outbound LLM calls."""
    monkeypatch.setattr(settings, "llm_enabled", True)

    for placeholder in ("", "sk-test", "sk-your-key-here"):
        monkeypatch.setattr(settings, "openai_api_key", placeholder)
        assert provider.is_llm_enabled() is False


def test_create_chat_model_uses_configured_settings(monkeypatch):
    """Provider should be the single place constructing ChatOpenAI clients."""
    captured_kwargs = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-real-looking-key")
    monkeypatch.setattr(settings, "openai_model", "test-model")
    monkeypatch.setattr(provider, "ChatOpenAI", FakeChatOpenAI)

    model = provider.create_chat_model(temperature=0.25, timeout=10)

    assert isinstance(model, FakeChatOpenAI)
    assert captured_kwargs == {
        "model": "test-model",
        "api_key": "sk-real-looking-key",
        "temperature": 0.25,
        "timeout": 10,
    }

