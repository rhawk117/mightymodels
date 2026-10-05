"""The Claude Code hook events the python-harness hooks answer."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal


class HookEvent(StrEnum):
    SESSION_START = 'SessionStart'
    PRE_TOOL_USE = 'PreToolUse'


@dataclass(frozen=True, slots=True)
class SessionStart:
    cwd: Path


@dataclass(frozen=True, slots=True)
class BashCall:
    command: str
    kind: Literal['bash'] = field(default='bash', init=False)


@dataclass(frozen=True, slots=True)
class OtherToolCall:
    tool_name: str
    kind: Literal['other_tool'] = field(default='other_tool', init=False)


type ToolCall = BashCall | OtherToolCall


SEARCH_BOUNDARY_MARKERS = ('.git', 'pyproject.toml')
