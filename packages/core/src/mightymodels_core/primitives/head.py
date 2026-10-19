"""The shortened form of a git head, as the tools print it."""

SHORT_SHA = 12


def short_head(head: str | None) -> str:
    return ('unknown' if head is None else head)[:SHORT_SHA]
