"""PII stripping service — regex-based detection and removal of emails,
phone numbers, and SSN patterns from text before storage."""
import re
from typing import Optional

# SSN: requires at least one separator to reduce false positives
_SSN_PATTERN = re.compile(r'\b\d{3}[-\s]\d{2}[-\s]\d{4}\b')

# Email
_EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# US phone numbers — covers (555) 123-4567, 555-123-4567, +1 555 123 4567, etc.
_PHONE_PATTERN = re.compile(
    r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
)


def strip_pii(text: Optional[str]) -> Optional[str]:
    """Remove PII patterns from text, replacing with tagged placeholders.

    Returns None if input is None (passthrough for optional fields).
    Order: SSN before phone to avoid partial matches.
    """
    if not text:
        return text

    text = _SSN_PATTERN.sub('[REDACTED_SSN]', text)
    text = _EMAIL_PATTERN.sub('[REDACTED_EMAIL]', text)
    text = _PHONE_PATTERN.sub('[REDACTED_PHONE]', text)

    return text
