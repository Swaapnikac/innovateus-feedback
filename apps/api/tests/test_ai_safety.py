"""Tests for the prompt-injection / PII-asking post-filter on AI follow-ups.

The model's follow-up question is the only AI-generated string that ever
reaches a learner. Even with the system prompt explicitly forbidding it,
a successful jailbreak (or a model glitch) could produce a question that
asks for personal information or echoes a real email/phone back. The
``_coerce_followups`` chokepoint drops any such candidate via
``_is_unsafe_followup`` and falls through to the existing "no follow-up"
path.
"""

from __future__ import annotations

import pytest

from app.services.ai_service import _coerce_followups, _is_unsafe_followup


@pytest.mark.parametrize(
    "text",
    [
        "What is your email?",
        "Could you share your home address?",
        "Tell us your phone number.",
        "What's your full name?",
        "Please share your SSN so we can follow up.",
        "What is your date of birth?",
        "What is your agency name?",
    ],
)
def test_unsafe_followup_pii_asking(text):
    assert _is_unsafe_followup(text) is True


def test_unsafe_followup_pii_echoed_back():
    # Model echoed a real email into the question — strip_pii should
    # detect it and the filter should drop the whole follow-up.
    assert (
        _is_unsafe_followup(
            "Could you share more detail? My email is foo@bar.com",
        )
        is True
    )


@pytest.mark.parametrize(
    "text",
    [
        "Could you share a specific example?",
        "What outcome did you see?",
        "Which task did you try first?",
        "Can you describe a workflow you applied this to?",
        "What got in the way when you tried it?",
    ],
)
def test_safe_followup_passes(text):
    assert _is_unsafe_followup(text) is False


def test_coerce_drops_only_unsafe_candidate():
    # Two candidates, one unsafe — the helper must drop the unsafe one
    # and keep the legitimate clarifier. Limit defaults to 1 so we get
    # exactly the safe one back.
    out = _coerce_followups(
        ["What is your email?", "Can you give a specific example?"],
        limit=2,
    )
    assert out == ["Can you give a specific example?"]


def test_coerce_drops_all_unsafe_returns_empty():
    # When every candidate is unsafe, the result is an empty list,
    # which the existing "declined" path handles cleanly downstream.
    out = _coerce_followups(["What is your phone number?"])
    assert out == []


def test_coerce_keeps_safe_string_input():
    # Backwards-compat: string input still works and isn't filtered
    # when it's a normal clarifier.
    out = _coerce_followups("Could you share an outcome you observed?")
    assert out == ["Could you share an outcome you observed?"]


def test_coerce_handles_none_and_garbage():
    # The shape-defenses still hold after the filter additions.
    assert _coerce_followups(None) == []
    assert _coerce_followups(123) == []
    assert _coerce_followups({"unrelated": "key"}) == []
