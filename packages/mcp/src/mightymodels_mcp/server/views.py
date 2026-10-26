"""The text helpers that concepts share when they report near-duplicates and matches."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.similarity.records import Duplicate, Match

EXCERPT_LENGTH = 120


def excerpt(text: str) -> str:
    one_line = ' '.join(text.split())
    return one_line if len(one_line) <= EXCERPT_LENGTH else f'{one_line[:EXCERPT_LENGTH]}...'


def match_line(match: Match) -> str:
    return f'{match.kind} {match.reference} (overlap {match.overlap:.2f}): {excerpt(match.text)}\n'


def duplicates_text(duplicates: Sequence[Duplicate]) -> str:
    return ''.join(
        f'near-duplicate: {duplicate.written} resembles {match_line(duplicate.earlier)}'
        for duplicate in duplicates
    )
