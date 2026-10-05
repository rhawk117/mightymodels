"""Secret redaction applied to every free-text field before it is stored."""

import re
from collections.abc import Mapping
from types import MappingProxyType

SECRET_PATTERNS: Mapping[str, re.Pattern[str]] = MappingProxyType(
    {
        'private-key': re.compile(
            r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
            re.DOTALL,
        ),
        'aws-key': re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'),
        'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_\w{20,})'),
        'slack-token': re.compile(r'\bxox[abposr]-[A-Za-z0-9-]{10,}'),
        'stripe-key': re.compile(r'\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b'),
        'api-key': re.compile(r'\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}'),
        'jwt': re.compile(r'\beyJ[\w-]+\.[\w-]+\.[\w-]+'),
        'bearer': re.compile(r'\bBearer [A-Za-z0-9._~+/-]{12,}=*'),
        'url-credentials': re.compile(r'(?<=://)[^/\s:@]+:[^@\s]+(?=@)'),
        'assignment': re.compile(
            r'(?i)[A-Z0-9_]*(?:password|passwd|secret|token|api[_-]?key)[A-Z0-9_]*'
            r'["\']?\s*[:=]\s*["\']?[^\s,;"\']+'
        ),
    }
)


def redact(text: str) -> str:
    for name, pattern in SECRET_PATTERNS.items():
        text = pattern.sub(f'[REDACTED:{name}]', text)
    return text
