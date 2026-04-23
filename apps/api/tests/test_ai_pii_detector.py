"""Unit tests for the GPT-5 PII detector layer in ``ai_service``.

These tests deliberately run WITHOUT a live OpenAI API key — they verify
that the detector falls back gracefully to regex-only redaction and
never echoes raw PII back to the caller.

Kept plugin-free by driving the coroutines through ``asyncio.run``.
"""

import asyncio
import pytest

from app.services import ai_service


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_cache_and_key(monkeypatch):
    ai_service._PII_CACHE.clear()
    monkeypatch.setattr(ai_service, "_has_api_key", lambda: False)
    yield
    ai_service._PII_CACHE.clear()


def test_empty_input_returns_empty():
    text, count, cats = _run(ai_service.detect_and_redact_pii_with_ai(""))
    assert text == ""
    assert count == 0
    assert cats == []


def test_regex_fallback_redacts_email_and_ssn():
    raw = "email me at john@gov.org or SSN 123-45-6789"
    text, count, cats = _run(ai_service.detect_and_redact_pii_with_ai(raw))
    assert "john@gov.org" not in text
    assert "123-45-6789" not in text
    assert "***" in text
    assert count >= 2
    assert "email" in cats and "ssn" in cats


def test_cache_hit_returns_same_object():
    raw = "call me 415-555-1234"
    first = _run(ai_service.detect_and_redact_pii_with_ai(raw))
    second = _run(ai_service.detect_and_redact_pii_with_ai(raw))
    assert first == second
    assert "***" in first[0]
    assert "phone" in first[2]


def test_ai_failure_falls_back_to_regex(monkeypatch):
    """When an API key is present but the AI call raises, we must still
    return regex-scrubbed text — never the raw input."""
    monkeypatch.setattr(ai_service, "_has_api_key", lambda: True)

    class _Boom:
        class chat:  # noqa: N801 — mimics openai client shape
            class completions:  # noqa: N801
                @staticmethod
                async def create(**_kwargs):
                    raise RuntimeError("simulated network failure")

    monkeypatch.setattr(ai_service, "_get_client", lambda: _Boom())
    monkeypatch.setattr(ai_service, "_load_prompt", lambda _name: "")

    raw = "ssn 123-45-6789 and 415-555-1234"
    text, count, _cats = _run(ai_service.detect_and_redact_pii_with_ai(raw))
    assert "123-45-6789" not in text
    assert "415-555-1234" not in text
    assert count >= 2


def test_ai_name_redaction_applied(monkeypatch):
    """When AI returns a name span, the detector must apply it on top of
    the regex layer and tag the ``name`` category."""
    monkeypatch.setattr(ai_service, "_has_api_key", lambda: True)
    monkeypatch.setattr(ai_service, "_load_prompt", lambda _name: "")

    class _FakeMessage:
        def __init__(self, content):
            self.content = content

    class _FakeChoice:
        def __init__(self, content):
            self.message = _FakeMessage(content)

    class _FakeResponse:
        def __init__(self, content):
            self.choices = [_FakeChoice(content)]

    class _FakeClient:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**_kwargs):
                    return _FakeResponse(
                        '{"redactions":[{"category":"person_name","span":"Jane Smith"}]}'
                    )

    monkeypatch.setattr(ai_service, "_get_client", lambda: _FakeClient())

    raw = "My manager Jane Smith was very supportive"
    text, count, cats = _run(ai_service.detect_and_redact_pii_with_ai(raw))
    assert "Jane Smith" not in text
    assert "***" in text
    assert "name" in cats
    assert count >= 1
