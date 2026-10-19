"""The errors of the ticket repository."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from mightymodels_core.primitives import Slug


class NotStagedError(StateError):
    def __init__(self, *, slug: Slug) -> None:
        self.slug = slug
        super().__init__(f'{slug} is not staged; stage the ticket with open-ticket first')


class ClosedTicketError(StateError):
    def __init__(self, *, slug: Slug) -> None:
        self.slug = slug
        super().__init__(
            f'{slug} is closed, and a closed ticket is final; '
            'new work needs a new ticket, staged with open-ticket'
        )


class UnknownInvestigationError(StateError):
    def __init__(self, *, slug: Slug, investigation_key: str) -> None:
        self.slug = slug
        self.investigation_key = investigation_key
        super().__init__(
            f'{slug} declares investigation {investigation_key!r}, which has no record'
        )


class InvalidTicketError(StateError):
    def __init__(self, *, problems: tuple[str, ...]) -> None:
        self.problems = problems
        super().__init__('ticket.yml is invalid:\n  ' + '\n  '.join(problems))
