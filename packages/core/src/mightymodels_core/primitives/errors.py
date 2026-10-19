"""The root of the mightymodels state errors and the errors of the value types."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


class StateError(Exception):
    pass


class InvalidSlugError(StateError):
    def __init__(self, *, raw: str, limit: int) -> None:
        self.raw = raw
        self.limit = limit
        super().__init__(
            f'{raw!r} is not a slug: letters, digits, dashes and underscores only, '
            f'starting with a letter or digit, at most {limit} characters'
        )


class ReservedSlugError(StateError):
    def __init__(self, *, raw: str) -> None:
        self.raw = raw
        super().__init__(f'{raw!r} is reserved for the archive directory')


class InvalidRunIdError(StateError):
    def __init__(self, *, raw: str) -> None:
        self.raw = raw
        super().__init__(f'run id {raw!r} is not valid: it is the UTC start time, YYYYMMDD-HHMMSS')


class InvalidTaskIdError(StateError):
    def __init__(self, *, raw: str, limit: int) -> None:
        self.raw = raw
        self.limit = limit
        super().__init__(
            f'task id {raw!r} is not valid: T, C or R and one to six digits, '
            f'at most {limit} characters'
        )


class InvalidRepositoryKeyError(StateError):
    def __init__(self, *, raw: str, limit: int) -> None:
        self.raw = raw
        self.limit = limit
        super().__init__(
            f'repository key {raw!r} is not valid: an owner/name pair or a local: digest, '
            f'at most {limit} characters'
        )


class NaiveClockTimeError(StateError):
    def __init__(self, *, moment: datetime) -> None:
        self.moment = moment
        super().__init__(f'clock time {moment.isoformat()} has no timezone')


class UnreadableJsonError(StateError):
    def __init__(self, *, detail: str) -> None:
        self.detail = detail
        super().__init__(f'the text is not JSON the codec reads: {detail}')
