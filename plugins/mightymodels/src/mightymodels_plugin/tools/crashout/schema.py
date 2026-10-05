"""Arguments and results of the `crashout` tool.

`CrashoutEntry` is one crashout as the caller reports it and `JournaledCrashout` is one as the
journal holds it, with the time it was journaled first. Both keep one field order, which is the
order the journal's text reads in.
"""

from enum import StrEnum, auto
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from mightymodels_plugin.slug import Slug

type NotBlank = Annotated[str, StringConstraints(pattern=r'\S')]
type Stripped = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
type Failures = Annotated[tuple[NotBlank, ...], Field(min_length=1)]


class CrashoutAction(StrEnum):
    ADD = auto()
    STATS = auto()
    LAST = auto()


class Severity(StrEnum):
    MILD_TILT = 'mild-tilt'
    HEATED = 'heated'
    CRASHOUT = 'crashout'
    FULL_MELTDOWN = 'full-meltdown'


class Verdict(StrEnum):
    DESERVED = auto()
    SPLIT = auto()
    UNREASONABLE = auto()


class CrashoutEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    ticket: Slug | None = None
    branch: str | None = None
    severity: Severity
    verdict: Verdict
    rant: NotBlank
    failures: Failures
    root_cause: Stripped
    corrective_action: Stripped
    barked_back: bool


class JournaledCrashout(BaseModel):
    model_config = ConfigDict(frozen=True)

    at: str
    ticket: str | None
    branch: str | None
    severity: Severity
    verdict: Verdict
    rant: str
    failures: tuple[str, ...]
    root_cause: str
    corrective_action: str
    barked_back: bool


class CrashoutView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    entry: JournaledCrashout | None = None
