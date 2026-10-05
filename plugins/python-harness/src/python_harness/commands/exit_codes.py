"""Process exit codes shared by every command group."""

from enum import IntEnum


class ExitCode(IntEnum):
    PASSED = 0
    FAILED = 1
    ERROR = 2


def exit_code_for(*, passed: bool) -> ExitCode:
    if passed:
        return ExitCode.PASSED
    return ExitCode.FAILED
