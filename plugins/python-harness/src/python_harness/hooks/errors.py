"""Hook payloads the handlers cannot read, reported instead of a traceback."""

from python_harness.core.errors import PythonHarnessError


class HookPayloadNotJsonError(PythonHarnessError):
    def __init__(self, reason: str) -> None:
        super().__init__(f'the hook payload on stdin is not JSON: {reason}')
        self.reason = reason


class HookPayloadNotObjectError(PythonHarnessError):
    def __init__(self, found: str) -> None:
        super().__init__(f'the hook payload on stdin is a JSON {found}, not an object')
        self.found = found


class HookFieldMissingError(PythonHarnessError):
    def __init__(self, name: str) -> None:
        super().__init__(f'the hook payload has no string field {name!r}')
        self.name = name


class HookEventMismatchError(PythonHarnessError):
    def __init__(self, expected: str, found: str) -> None:
        super().__init__(f'this handler answers {expected} events, not {found}')
        self.expected = expected
        self.found = found
