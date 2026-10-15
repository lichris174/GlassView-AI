"""Pattern-based PII / secret redaction.

The screen copilot captures whatever is on screen, which routinely includes
emails, tokens, and keys. Before any of that text is stored in the RAG memory
or written to a log, it is run through :func:`redact`, which replaces matches
with ``[REDACTED:TYPE]`` markers. This is a guard, not a guarantee: it favours
recall on the high-signal secret formats while keeping false positives low
(card numbers are Luhn-checked) so stored memories stay readable.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    kind: str
    value: str


def _luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if len(nums) < 13:
        return False
    total = 0
    for i, n in enumerate(reversed(nums)):
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# Order matters: multi-line/structured secrets first, then specific tokens,
# then PII, then the broad key=value catch-all so it does not mask a better tag.
_RULES: list[tuple[str, re.Pattern[str], Callable[[str], bool] | None]] = [
    (
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        None,
    ),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), None),
    ("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), None),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), None),
    ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), None),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), None),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), None),
    (
        "CREDIT_CARD",
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        _luhn_ok,
    ),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)"), None),
    (
        "SECRET",
        re.compile(
            r"""(?ix)
            \b(?:api[_-]?key|secret|token|passwd|password|access[_-]?key)\b
            \s*[:=]\s*
            ['"]?(?P<v>[A-Za-z0-9/+_\-]{8,})['"]?
            """
        ),
        None,
    ),
]


def scan(text: str) -> list[Finding]:
    """Return all detected secrets / PII without modifying the text."""
    findings: list[Finding] = []
    for kind, pattern, validator in _RULES:
        for m in pattern.finditer(text):
            value = m.group("v") if "v" in m.groupdict() and m.groupdict()["v"] else m.group(0)
            if validator and not validator(value):
                continue
            findings.append(Finding(kind=kind, value=value))
    return findings


def redact(text: str) -> tuple[str, list[Finding]]:
    """Replace detected secrets / PII with ``[REDACTED:KIND]`` markers.

    Returns the cleaned text and the list of findings (with their original
    values, so a caller can decide whether to refuse to store at all).
    """
    findings: list[Finding] = []
    out = text
    for kind, pattern, validator in _RULES:
        def _sub(m: re.Match[str], kind: str = kind, validator=validator) -> str:
            gd = m.groupdict()
            value = gd["v"] if gd.get("v") else m.group(0)
            if validator and not validator(value):
                return m.group(0)
            findings.append(Finding(kind=kind, value=value))
            if gd.get("v"):
                # Keep the label/assignment, mask only the secret value.
                return m.group(0).replace(value, f"[REDACTED:{kind}]")
            return f"[REDACTED:{kind}]"

        out = pattern.sub(_sub, out)
    return out, findings
