"""What the guard treats as plain python, what it suggests instead, and its verdicts."""

import re
from dataclasses import dataclass, field
from typing import Literal

INTERPRETER_NAME = re.compile(r'python(?:\d+(?:\.\d+t?)?)?')


@dataclass(frozen=True, slots=True)
class GuardOptions:
    interpreter: re.Pattern[str] = INTERPRETER_NAME
    interpreter_names: str = 'python, python3 or pythonX.Y'
    runner_prefix: str = 'uv run'
    max_listed_calls: int = 10
    shown_command_characters: int = 200

    @property
    def replacement(self) -> str:
        return f'{self.runner_prefix} python'


@dataclass(frozen=True, slots=True)
class InterpreterCall:
    interpreter: str
    command: str
    suggestion: str


@dataclass(frozen=True, slots=True)
class Nudge:
    calls: tuple[InterpreterCall, ...]
    kind: Literal['nudge'] = field(default='nudge', init=False)


@dataclass(frozen=True, slots=True)
class NoNudge:
    kind: Literal['no_nudge'] = field(default='no_nudge', init=False)


type GuardVerdict = Nudge | NoNudge
