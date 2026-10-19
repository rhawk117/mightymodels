"""The errors of the investigation repository."""

from mightymodels_core.primitives import StateError


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
