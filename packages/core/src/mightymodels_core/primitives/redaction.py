"""Secret redaction applied to every free-text field before it is stored.

A marker can be longer than the secret it replaces, so text a request accepted at the length of
its column can leave redaction over it. `redact_within` and `redaction_within` redact text on its
way to a column and refuse it when the redacted text is over the limit the caller names. The text
is never cut to fit and the secret is never kept.
"""

import re
from dataclasses import dataclass, field
from functools import cache
from typing import Literal, NewType

from .errors import RedactedTextTooLongError

RedactedText = NewType('RedactedText', str)

type PatternName = Literal[
    'private-key',
    'aws-key',
    'github-token',
    'slack-token',
    'stripe-key',
    'api-key',
    'jwt',
    'bearer',
    'url-credentials',
    'assignment',
]


@dataclass(slots=True, kw_only=True, frozen=True)
class SecretPatterns:
    """The secret patterns by name; they apply in the order they were added."""

    by_name: dict[PatternName, re.Pattern[str]] = field(default_factory=dict)

    def add(self, name: PatternName, source: str, flags: int = 0) -> None:
        self.by_name[name] = re.compile(source, flags)

    def scrub(self, text: str) -> tuple[str, int]:
        hits = 0
        for name, pattern in self.by_name.items():
            text, replaced = pattern.subn(f'[REDACTED:{name}]', text)
            hits += replaced
        return text, hits


def create_secret_patterns() -> SecretPatterns:
    patterns = SecretPatterns()
    patterns.add(
        'private-key',
        r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
        re.DOTALL,
    )
    patterns.add('aws-key', r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b')
    patterns.add('github-token', r'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_\w{20,})')
    patterns.add('slack-token', r'\bxox[abposr]-[A-Za-z0-9-]{10,}')
    patterns.add('stripe-key', r'\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b')
    patterns.add('api-key', r'\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}')
    patterns.add('jwt', r'\beyJ[\w-]+\.[\w-]+\.[\w-]+')
    patterns.add('bearer', r'\bBearer [A-Za-z0-9._~+/-]{12,}=*')
    patterns.add('url-credentials', r'(?<=://)[^/\s:@]+:[^@\s]+(?=@)')
    patterns.add(
        'assignment',
        r'(?i)(?<![A-Z0-9_])'
        r'(?:(?>[A-Z0-9_]*?(?:password|passwd|secret|token|api_?key))[A-Z0-9_]*+'
        r'|[A-Z0-9_]*+(?<=api)-key[A-Z0-9_]*+)'
        r'["\']?\s*[:=]\s*["\']?[^\s,;"\']+',
    )
    return patterns


@cache
def default_secret_patterns() -> SecretPatterns:
    return create_secret_patterns()


@dataclass(slots=True, kw_only=True, frozen=True)
class Redaction:
    text: RedactedText
    hits: int

    def length_error(self, field: str, limit: int) -> RedactedTextTooLongError | None:
        if len(self.text) <= limit:
            return None
        return RedactedTextTooLongError(field=field, limit=limit, length=len(self.text))


def redact(text: str) -> RedactedText:
    scrubbed, _ = default_secret_patterns().scrub(text)
    return RedactedText(scrubbed)


def redaction_of(text: str) -> Redaction:
    _, hits = default_secret_patterns().scrub(text)
    return Redaction(text=redact(text), hits=hits)


def redaction_within(text: str, field: str, limit: int) -> Redaction:
    redaction = redaction_of(text)
    if (error := redaction.length_error(field, limit)) is not None:
        raise error
    return redaction


def redact_within(text: str, field: str, limit: int) -> RedactedText:
    return redaction_within(text, field, limit).text
