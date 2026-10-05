"""Pure text helpers every concept shares: whitespace runs collapsed to one space."""


def collapse_whitespace(text: str) -> str:
    return ' '.join(text.split())
