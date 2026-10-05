"""Arguments and results of the `contract` tool, and the receipt `verify run` records."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

COMMAND_ID_PATTERN = r'^[A-Za-z0-9._-]+$'
DEFAULT_TIMEOUT = 300
MAX_TIMEOUT = 3600


class ShellStringError(ValueError):
    def __init__(self) -> None:
        super().__init__('argv must be a non-empty list of strings; no shell string')


def checked_argv(value: object) -> object:
    is_list = isinstance(value, (list, tuple)) and bool(value)
    if not is_list or not all(isinstance(argument, str) for argument in value):
        raise ShellStringError
    return value


type CommandId = Annotated[str, StringConstraints(pattern=COMMAND_ID_PATTERN)]
type Argv = Annotated[tuple[str, ...], BeforeValidator(checked_argv)]
type Timeout = Annotated[int, Field(ge=1, le=MAX_TIMEOUT)]


class ContractAction(StrEnum):
    APPROVE = 'approve'
    STATUS = 'status'


class Phase(StrEnum):
    PLANNING = 'planning'
    TASK = 'task'
    REVIEW = 'review'
    LANDING = 'landing'


class Outcome(StrEnum):
    PASSED = 'pass'
    FAILED = 'fail'
    TIMEOUT = 'timeout'
    NOT_FOUND = 'not-found'


class ContractCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    id: CommandId
    argv: Argv
    expect_exit: int = 0
    timeout: Timeout = DEFAULT_TIMEOUT
    approved_by: str = ''


class CommandState(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    argv: tuple[str, ...]
    state: str


class ContractView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    passing: bool
    commands: tuple[CommandState, ...] = ()
