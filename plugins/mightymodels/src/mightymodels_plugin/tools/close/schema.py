"""Arguments and results of the `close` tool.

`Closing` is what the user says about the ticket as it closes. `ArchiveRecord` is the JSON
prune-ticket writes beside the archive Markdown, and `ClosedArchive` carries both texts with
their paths. The record's ledger decisions, worker runs and recorded answers read empty: the
database holds no row for them yet.
"""

from enum import StrEnum, auto

from pydantic import BaseModel, ConfigDict, Field

from mightymodels_plugin.routing import Depth
from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.snapshot.schema import NotYetRecorded
from mightymodels_plugin.tools.task.schema import Status
from mightymodels_plugin.tools.ticket.schema import Tracker


class CloseAction(StrEnum):
    CHECK = auto()
    CLOSE = auto()


class Closing(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    shipped: str = ''
    pr: str | None = None
    gotchas: tuple[str, ...] = ()


class ArchivedTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Status
    attempts: dict[str, int]


class ArchivedCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    argv: tuple[str, ...]
    expect_exit: int
    outcome: str
    head: str | None
    digest: str | None


class ArchivedReview(BaseModel):
    model_config = ConfigDict(frozen=True)

    run: str
    depth: Depth
    findings: int
    by_decision: dict[str, tuple[str, ...]]
    reasons: dict[str, str]


class WorkerRuns(BaseModel):
    model_config = ConfigDict(frozen=True)

    runs: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    recent: NotYetRecorded = ()


class RecordedAnswers(BaseModel):
    model_config = ConfigDict(frozen=True)

    recorded: int = 0
    recent: NotYetRecorded = ()


class ArchiveRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: Slug
    closed_at: str
    head: str | None
    shipped: str
    pr: str | None
    tracker: Tracker
    summary: str
    investigations: tuple[str, ...]
    tasks: dict[str, ArchivedTask]
    verification: tuple[ArchivedCommand, ...]
    decisions: NotYetRecorded = ()
    review: ArchivedReview | None
    agents: WorkerRuns = WorkerRuns()
    answers: RecordedAnswers = RecordedAnswers()
    gotchas: tuple[str, ...]


class ClosedArchive(BaseModel):
    model_config = ConfigDict(frozen=True)

    markdown: str
    record: ArchiveRecord
    markdown_path: str
    record_path: str


class CloseView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    blocked: bool
    blockers: tuple[str, ...] = ()
    archive: ClosedArchive | None = None
