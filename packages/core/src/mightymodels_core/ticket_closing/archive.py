"""The archive record of a closed ticket, built from values the close service read.

It is a frozen value with no wording: the Markdown renderer takes it, and the caller writes the
archive files. Every prose field is redacted text and one line, so the renderer can place it in
a list item.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from mightymodels_core.primitives import redact
from mightymodels_core.ticket_closing.policy import one_line

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mightymodels_core.contract.records import Receipt, RecordedCommand
    from mightymodels_core.investigations.ledger import Ledger
    from mightymodels_core.primitives import RedactedText, RunId, Slug, TaskId
    from mightymodels_core.reviews.records import DecidedFinding
    from mightymodels_core.reviews.services import LatestReview
    from mightymodels_core.tasks.records import AttemptCounts, TaskRecord
    from mightymodels_core.ticket_closing.records import ClosingRecord
    from mightymodels_core.tickets.records import TicketRecord, Tracker
    from mightymodels_core.vocabulary.contract import Outcome
    from mightymodels_core.vocabulary.reviews import Depth
    from mightymodels_core.vocabulary.tasks import TaskStatus, Worker

type CommandOutcome = Outcome | Literal['never-run']


@dataclass(slots=True, kw_only=True, frozen=True)
class ArchivedTask:
    status: TaskStatus
    attempts: Mapping[Worker, int]


@dataclass(slots=True, kw_only=True, frozen=True)
class ArchivedCommand:
    key: str
    argv: tuple[str, ...]
    expect_exit: int
    outcome: CommandOutcome
    head: str | None
    digest: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ArchivedReview:
    run: RunId
    depth: Depth
    findings: int
    by_decision: Mapping[str, tuple[str, ...]]
    reasons: Mapping[str, RedactedText]


@dataclass(slots=True, kw_only=True, frozen=True)
class ArchivedDecision:
    text: RedactedText
    origin: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ArchiveRecord:
    slug: Slug
    tracker: Tracker
    summary: RedactedText
    investigations: tuple[str, ...]
    closing: ClosingRecord
    tasks: Mapping[TaskId, ArchivedTask]
    verification: tuple[ArchivedCommand, ...]
    decisions: tuple[ArchivedDecision, ...]
    review: ArchivedReview | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ArchiveSources:
    ticket: TicketRecord
    closing: ClosingRecord
    tasks: Sequence[TaskRecord]
    attempts: AttemptCounts
    commands: Sequence[RecordedCommand]
    receipts: Mapping[str, Receipt]
    ledgers: Sequence[Ledger]
    review: LatestReview | None
    decision_limit: int


def archived_command(command: RecordedCommand, receipt: Receipt | None) -> ArchivedCommand:
    if receipt is None:
        return ArchivedCommand(
            key=command.key,
            argv=command.argv,
            expect_exit=command.expect_exit,
            outcome='never-run',
            head=None,
            digest=None,
        )

    return ArchivedCommand(
        key=command.key,
        argv=command.argv,
        expect_exit=command.expect_exit,
        outcome=receipt.outcome,
        head=receipt.head,
        digest=receipt.digest,
    )


def decision_label(review: LatestReview, disposition: DecidedFinding) -> str:
    if review.is_fixed(disposition.finding_key):
        return review.options.fixed_result

    return disposition.decision


def archived_review(review: LatestReview | None) -> ArchivedReview | None:
    if review is None:
        return None

    labels = {
        disposition.finding_key: decision_label(review, disposition)
        for disposition in review.decided
    }
    return ArchivedReview(
        run=review.run.run_id,
        depth=review.run.depth,
        findings=len(review.findings),
        by_decision={
            label: tuple(key for key, held in labels.items() if held == label)
            for label in dict.fromkeys(labels.values())
        },
        reasons={
            disposition.finding_key: redact(one_line(disposition.reason))
            for disposition in review.decided
            if disposition.reason
        },
    )


def archived_decisions(ledgers: Sequence[Ledger], limit: int) -> tuple[ArchivedDecision, ...]:
    decisions = [
        ArchivedDecision(text=redact(one_line(record.text)), origin=ledger.origin_of(record))
        for ledger in ledgers
        for record in ledger.live_of_kind('decision')
    ]
    return tuple(decisions[max(len(decisions) - limit, 0) :])


def create_archive_record(sources: ArchiveSources) -> ArchiveRecord:
    ticket = sources.ticket
    return ArchiveRecord(
        slug=ticket.slug,
        tracker=ticket.section.tracker,
        summary=ticket.section.summary,
        investigations=ticket.investigations,
        closing=sources.closing,
        tasks={
            task.key: ArchivedTask(status=task.status, attempts=sources.attempts.get(task.key, {}))
            for task in sources.tasks
        },
        verification=tuple(
            archived_command(command, sources.receipts.get(command.key))
            for command in sources.commands
        ),
        decisions=archived_decisions(sources.ledgers, sources.decision_limit),
        review=archived_review(sources.review),
    )
