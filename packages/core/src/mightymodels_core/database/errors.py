"""Domain errors of the database adapter: one class per failure, none of them a `sqlite3` error."""


class DatabaseError(Exception):
    pass


class DuplicateBlockError(DatabaseError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'statement block {name!r} appears more than once')


class EmptyBlockError(DatabaseError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'statement block {name!r} holds no SQL')


class DuplicateDeclarationError(DatabaseError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'statement {name!r} is declared more than once')


class MissingBlockError(DatabaseError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'statement {name!r} is declared but has no block')


class UndeclaredBlockError(DatabaseError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'statement block {name!r} has no declaration')


class NaiveTimestampError(DatabaseError):
    def __init__(self, *, field: str) -> None:
        self.field = field
        super().__init__(f'parameter {field!r} is a datetime without a timezone')


class RowDecodeError(DatabaseError):
    def __init__(self, *, statement: str, detail: str) -> None:
        self.statement = statement
        self.detail = detail
        super().__init__(f'statement {statement!r} returned a row that does not decode: {detail}')
