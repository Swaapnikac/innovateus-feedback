"""PII stripping service.

Goal: guarantee that personally identifiable information never lands in the
database and never reaches OpenAI.

``strip_pii`` is cheap and deterministic (regex-only). It runs on every write
path and on every payload we hand to OpenAI. For free-form PII that regex
cannot catch reliably (participant names, unstructured addresses, business
contact blocks), a GPT-5-based redactor in ``ai_service`` layers on top — see
``ai_service.detect_and_redact_pii_with_ai``.

Public API:
    strip_pii(text) -> cleaned text (backwards-compatible)
    strip_pii_with_meta(text) -> (cleaned, count, categories)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Pattern library
# ──────────────────────────────────────────────────────────────────────────────
# Order matters: more specific / longer-match patterns should run first so the
# generic ones don't swallow their digits.

# --- Financial / identity -----------------------------------------------------
# SSN with separators (e.g. 123-45-6789 or 123 45 6789)
_SSN_WITH_SEP = re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b")

# 9-digit SSN without separators. We require SSN-like context words nearby so
# that 9-digit order numbers / tracking IDs don't get falsely redacted.
_SSN_NO_SEP = re.compile(
    r"(?i)\b(?:ssn|social\s*security(?:\s*number)?|soc\s*sec)\b[^\d]{0,15}(\d{9})\b"
)

# Credit-card-like sequences (13-19 digits, optional separators). Validated
# with Luhn in post-processing below so random long numbers don't match.
_CREDIT_CARD_CANDIDATE = re.compile(
    r"\b(?:\d[ -]?){12,18}\d\b"
)

# Driver's license style: 1-2 letters + 6-8 digits (covers many US states)
_DRIVER_LICENSE = re.compile(
    r"(?i)\b(?:dl|driver'?s?\s+license|license)[^A-Z0-9]{0,10}([A-Z]{1,2}\d{6,8})\b"
)

# Bank account / routing number context (keeps digits only if preceded by label)
_BANK_ACCOUNT = re.compile(
    r"(?i)\b(?:account|acct|routing)(?:\s*(?:number|no\.?|#))?\s*[:#]?\s*(\d{6,17})\b"
)

# --- Contact information ------------------------------------------------------
# Email
_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# US phone numbers (with or without country code). Accepts (555) 123-4567,
# 555-123-4567, +1 555 123 4567, 555.123.4567, etc.
_US_PHONE = re.compile(
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
)

# International phone (e.g., +44 20 7946 0958). Runs AFTER US phone so we
# don't double-redact.
_INTL_PHONE = re.compile(r"\+\d{1,3}[-.\s]?\d[\d\s\-.]{6,14}\d\b")

# IPv4
_IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
)

# --- Location -----------------------------------------------------------------
# Street address: house number + street name + street suffix.
# Intentionally conservative — we key on a recognised suffix keyword.
_STREET_ADDRESS = re.compile(
    r"(?i)\b\d{1,6}\s+[A-Z][a-zA-Z0-9\-'.]*(?:\s+[A-Z][a-zA-Z0-9\-'.]*){0,4}\s+"
    r"(?:street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|lane|ln\.?|"
    r"drive|dr\.?|way|court|ct\.?|place|pl\.?|terrace|ter\.?|parkway|pkwy\.?|"
    r"highway|hwy\.?|circle|cir\.?|square|sq\.?|trail|trl\.?)\b"
)

# US ZIP code (5-digit or ZIP+4) — only when a street/address context is
# visible to avoid clobbering standalone years like 12345.
_ZIP_CODE = re.compile(
    r"(?i)\b(?:zip\s*(?:code)?\s*[:#]?\s*)?(\d{5}(?:-\d{4})?)\b(?=[\s,.!?)\]]|$)"
)

# --- Dates / birth ------------------------------------------------------------
# DOB numeric: 01/23/1985, 1/2/85, 23-01-1985, 23.01.1985
_DOB_NUMERIC = re.compile(
    r"(?i)(?:\bdob\b|\bdate\s+of\s+birth\b|\bborn(?:\s+on)?\b)[^\d]{0,10}"
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})"
)

# DOB spelled out: "January 23, 1985"
_DOB_SPELLED = re.compile(
    r"(?i)(?:\bdob\b|\bdate\s+of\s+birth\b|\bborn(?:\s+on)?\b)[^A-Z]{0,10}"
    r"((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2},?\s+\d{4})"
)

# Generic numeric date (not tied to DOB context) — optional pattern for
# stripping explicit date-of-birth mentions without context keyword. Kept
# conservative: exactly yyyy-mm-dd or mm/dd/yyyy that looks date-like.
_DATE_LIKE = re.compile(
    r"\b(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}\b"
    r"|\b(?:19|20)\d{2}[\-/](?:0?[1-9]|1[0-2])[\-/](?:0?[1-9]|[12]\d|3[01])\b"
)


# ──────────────────────────────────────────────────────────────────────────────
# Public helpers
# ──────────────────────────────────────────────────────────────────────────────

# Single neutral placeholder for every redaction, regardless of category. The
# category name is still tracked on ``RedactionResult.categories`` and persisted
# on the Submission row, so analytics/audit isn't lost — the user-visible text
# just looks cleaner than ``[REDACTED_PHONE]``.
REDACTED_TOKEN = "***"


@dataclass
class RedactionResult:
    text: str
    count: int
    categories: list[str]

    @property
    def changed(self) -> bool:
        return self.count > 0


def _luhn_ok(digits_only: str) -> bool:
    total = 0
    reverse = digits_only[::-1]
    for i, ch in enumerate(reverse):
        if not ch.isdigit():
            return False
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _redact_credit_cards(text: str, counter: dict) -> str:
    def replace(match: re.Match) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            counter["count"] += 1
            counter["cats"].add("credit_card")
            return REDACTED_TOKEN
        return raw

    return _CREDIT_CARD_CANDIDATE.sub(replace, text)


def _redact_zip_near_address(text: str, counter: dict) -> str:
    """Only redact ZIP if a street-suffix keyword appears within 60 chars of
    the candidate. This avoids catching standalone 5-digit numbers like
    population counts or page IDs.
    """
    suffix_keywords = re.compile(
        r"(?i)(?:street|st\.|avenue|ave\.|road|rd\.|boulevard|blvd\.|lane|ln\.|"
        r"drive|dr\.|way|court|ct\.|place|pl\.|\bcity\b|\bstate\b|"
        r"\bzip\b|\bpostal\b)"
    )

    def replace(match: re.Match) -> str:
        start = max(0, match.start() - 60)
        end = min(len(text), match.end() + 60)
        window = text[start:end]
        explicit = re.search(r"(?i)\bzip\b|\bpostal\b", window)
        nearby_address = suffix_keywords.search(window)
        if explicit or nearby_address:
            counter["count"] += 1
            counter["cats"].add("zip")
            return REDACTED_TOKEN
        return match.group(0)

    return _ZIP_CODE.sub(replace, text)


def _count_sub(pattern: re.Pattern, repl: str, text: str, cat: str, counter: dict) -> str:
    new_text, n = pattern.subn(repl, text)
    if n:
        counter["count"] += n
        counter["cats"].add(cat)
    return new_text


def _group1_sub(pattern: re.Pattern, replacement: str, text: str, cat: str, counter: dict) -> str:
    """Replace ``match.group(1)`` with ``replacement`` while keeping the
    surrounding match context intact. Increments the counter by the number
    of matches actually replaced.
    """
    n = 0

    def _do(match: re.Match) -> str:
        nonlocal n
        n += 1
        return match.group(0).replace(match.group(1), replacement)

    new_text = pattern.sub(_do, text)
    if n:
        counter["count"] += n
        counter["cats"].add(cat)
    return new_text


def strip_pii_with_meta(text: Optional[str]) -> RedactionResult:
    """Return cleaned text + how many redactions ran + which categories fired.

    Safe for ``None`` / empty input.
    """
    if not text:
        return RedactionResult(text=text or "", count=0, categories=[])

    counter = {"count": 0, "cats": set()}

    # Order: most specific first. Every redaction collapses to REDACTED_TOKEN
    # so the participant sees a single consistent placeholder ("***"); the
    # specific category is kept on ``counter["cats"]``.
    text = _count_sub(_SSN_WITH_SEP, REDACTED_TOKEN, text, "ssn", counter)
    text = _group1_sub(_SSN_NO_SEP, REDACTED_TOKEN, text, "ssn", counter)
    text = _group1_sub(_DRIVER_LICENSE, REDACTED_TOKEN, text, "license", counter)
    text = _group1_sub(_BANK_ACCOUNT, REDACTED_TOKEN, text, "account", counter)

    text = _redact_credit_cards(text, counter)
    text = _count_sub(_EMAIL, REDACTED_TOKEN, text, "email", counter)
    text = _count_sub(_US_PHONE, REDACTED_TOKEN, text, "phone", counter)
    text = _count_sub(_INTL_PHONE, REDACTED_TOKEN, text, "phone", counter)

    text = _group1_sub(_DOB_NUMERIC, REDACTED_TOKEN, text, "dob", counter)
    text = _group1_sub(_DOB_SPELLED, REDACTED_TOKEN, text, "dob", counter)

    text = _count_sub(_DATE_LIKE, REDACTED_TOKEN, text, "date", counter)
    text = _count_sub(_STREET_ADDRESS, REDACTED_TOKEN, text, "address", counter)
    text = _redact_zip_near_address(text, counter)
    text = _count_sub(_IPV4, REDACTED_TOKEN, text, "ip", counter)

    return RedactionResult(
        text=text,
        count=counter["count"],
        categories=sorted(counter["cats"]),
    )


def strip_pii(text: Optional[str]) -> Optional[str]:
    """Remove PII from ``text``.

    Backwards-compatible wrapper around :func:`strip_pii_with_meta` — returns
    only the cleaned string so existing call sites keep working.
    """
    if text is None:
        return None
    if not text:
        return text
    return strip_pii_with_meta(text).text
