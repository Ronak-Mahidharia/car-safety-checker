"""A second safety net for complaint text we commit to the repo.

NHTSA already removes personal details before publishing complaints. This also masks
anything that still looks like an email address, a phone number, or a full 17-character VIN.
"""
from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),                                      # email
    re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),  # US phone
    re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"),                                         # VIN (no I, O, Q)
]
MASK = "[removed]"


def scrub(text: str) -> str:
    """Return the text with emails, phone numbers, and full VINs masked."""
    for pattern in _PATTERNS:
        text = pattern.sub(MASK, text)
    return text
