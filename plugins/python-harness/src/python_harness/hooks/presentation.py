"""Markdown both hooks write: code spans that survive backticks, and short lines."""

ELLIPSIS = '...'


def code_span(text: str) -> str:
    if '`' in text:
        return f'`` {text} ``'
    return f'`{text}`'


def shorten_line(text: str, limit: int) -> str:
    lines = text.splitlines() or ['']
    first = lines[0]
    if len(first) > limit:
        return first[:limit] + ELLIPSIS
    if len(lines) > 1:
        return f'{first} {ELLIPSIS}'
    return first
