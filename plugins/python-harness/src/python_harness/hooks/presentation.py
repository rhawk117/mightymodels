"""Markdown both hooks write: code spans that survive backticks, and short lines."""

import re

ELLIPSIS = '...'
BACKTICK_RUN = re.compile(r'`+')


def code_span(text: str) -> str:
    longest_run = max(map(len, BACKTICK_RUN.findall(text)), default=0)
    if longest_run == 0:
        return f'`{text}`'
    delimiter = '`' * (longest_run + 1)
    return f'{delimiter} {text} {delimiter}'


def shorten_line(text: str, limit: int) -> str:
    lines = text.splitlines() or ['']
    first = lines[0]
    if len(first) > limit:
        return first[:limit] + ELLIPSIS
    if len(lines) > 1:
        return f'{first} {ELLIPSIS}'
    return first
