"""The errors of the investigation repository and the investigation rules."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.vocabulary.investigations import EntryKind, EntrySource


class InvestigationNotFoundError(StateError):
    def __init__(self, *, investigation_key: str) -> None:
        self.investigation_key = investigation_key
        super().__init__(f'no investigation {investigation_key!r}; add it before recording entries')


class DuplicateInvestigationError(StateError):
    def __init__(self, *, investigation_key: str) -> None:
        self.investigation_key = investigation_key
        super().__init__(f'investigation {investigation_key!r} already exists')


class DuplicateEntryError(StateError):
    def __init__(self, *, investigation_key: str, seq: int) -> None:
        self.investigation_key = investigation_key
        self.seq = seq
        super().__init__(f'investigation {investigation_key!r} already holds an entry {seq}')


class UnknownInvestigationError(StateError):
    def __init__(self, *, investigation_key: str) -> None:
        self.investigation_key = investigation_key
        super().__init__(f'no investigation named {investigation_key!r}; run list')


class RoundRegressionError(StateError):
    def __init__(self, *, given: int, latest: int) -> None:
        self.given = given
        self.latest = latest
        super().__init__(f'round {given} is earlier than the latest round {latest}')


class InvalidEntryError(StateError):
    def __init__(self, *, index: int, reason: str) -> None:
        self.index = index
        self.reason = reason
        super().__init__(f'entry {index}: {reason}')


class EmptyTextError(InvalidEntryError):
    def __init__(self, *, index: int) -> None:
        super().__init__(index=index, reason='text is empty')


class CiteRequiredError(InvalidEntryError):
    def __init__(self, *, index: int, kind: EntryKind) -> None:
        self.kind = kind
        reason = f'a {kind} entry needs a cite (file:line, URL#heading, or path)'
        super().__init__(index=index, reason=reason)


class SourceNotAllowedError(InvalidEntryError):
    def __init__(self, *, index: int, kind: EntryKind, source: EntrySource) -> None:
        self.kind = kind
        self.source = source
        super().__init__(index=index, reason=f'a {kind} entry cannot come from {source}')


class UnknownSupersededError(InvalidEntryError):
    def __init__(self, *, index: int, unknown: Sequence[int]) -> None:
        self.unknown = tuple(unknown)
        super().__init__(index=index, reason=f'supersedes unknown entries {list(unknown)}')
