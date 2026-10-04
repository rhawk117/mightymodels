import textwrap

DOCSTRING_SINGLE_LINE_LIMIT = 92
DOCSTRING_WIDTH = 88


def wrap_literal(text: str, width: int = 80) -> str:
    """Python source for `text` as one string literal, or a parenthesized run of them."""
    parts: list[str] = []
    current = ''
    for word in text.split(' '):
        candidate = f'{current} {word}' if current else word
        if len(candidate) > width and current:
            parts.append(current + ' ')
            current = word
        else:
            current = candidate
    parts.append(current)
    literals = [repr(part) for part in parts]
    return literals[0] if len(literals) == 1 else '(\n    ' + '\n    '.join(literals) + '\n)'


def docstring(title: str, text: str) -> str:
    """A docstring of `title: text` that no quote or backslash in the text can break out of."""
    body = ' '.join(f'{title}: {text}'.split()).replace('\\', '/').replace('"', "'")
    if len(body) <= DOCSTRING_SINGLE_LINE_LIMIT:
        return f'"""{body}"""'
    return '"""' + '\n'.join(textwrap.wrap(body, DOCSTRING_WIDTH)) + '\n"""'
