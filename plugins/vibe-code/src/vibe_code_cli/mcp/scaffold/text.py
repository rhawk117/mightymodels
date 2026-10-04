import textwrap

DOCSTRING_SINGLE_LINE_LIMIT = 92
DOCSTRING_WIDTH = 88


def wrap_literal(text: str, width: int = 80) -> str:
    parts: list[str] = []
    current = ''
    for word in text.split(' '):
        candidate = f'{current} {word}' if current else word
        if len(candidate) > width and current:
            parts.append(current + ' ')
            candidate = word
        current = candidate
    parts.append(current)
    literals = [repr(part) for part in parts]
    return literals[0] if len(literals) == 1 else '(\n    ' + '\n    '.join(literals) + '\n)'


def docstring(title: str, text: str) -> str:
    body = ' '.join(f'{title}: {text}'.split()).replace('\\', '/').replace('"', "'")
    if len(body) <= DOCSTRING_SINGLE_LINE_LIMIT:
        return f'"""{body}"""'
    return '"""' + '\n'.join(textwrap.wrap(body, DOCSTRING_WIDTH)) + '\n"""'
