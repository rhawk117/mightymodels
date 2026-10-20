"""The refusal a read unit of work adds to the ones the database already raises."""

from mightymodels_core.primitives import StateError


class UnknownRepositoryError(StateError):
    def __init__(self, *, repository_key: str) -> None:
        self.repository_key = repository_key
        super().__init__(
            f'no repository is recorded for {repository_key!r}; a write unit of work '
            'records it on first use'
        )
