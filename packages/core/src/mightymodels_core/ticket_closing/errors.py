"""The errors of the close service."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import Slug


class LiveWorkRemainsError(StateError):
    def __init__(self, *, slug: Slug, blockers: Sequence[str], git_refusal: str | None) -> None:
        self.slug = slug
        self.blockers = tuple(blockers)
        self.git_refusal = git_refusal
        listed = ''.join(f'\n  - {blocker}' for blocker in blockers)
        super().__init__(f'{slug} is not closed; live work remains:{listed}')


class ShippedRequiredError(StateError):
    def __init__(self) -> None:
        super().__init__('shipped is required: what this ticket delivered, one line')


class TooManyGotchasError(StateError):
    def __init__(self, *, given: int, limit: int) -> None:
        self.given = given
        self.limit = limit
        super().__init__(
            f'{given} gotchas is over the {limit} a closing may have; '
            'the rest belong in the docs or nowhere'
        )


class TicketMovedError(StateError):
    def __init__(self, *, slug: Slug, changed: Sequence[str]) -> None:
        self.slug = slug
        self.changed = tuple(changed)
        super().__init__(
            f'{slug} changed while git was asked ({", ".join(changed)}); nothing was written, '
            'close the ticket again'
        )
