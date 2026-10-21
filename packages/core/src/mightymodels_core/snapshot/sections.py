"""The functions that turn stored rows into the sections of a snapshot.

Each one is pure: it takes the rows a store returned and the caller's display limit, and returns a
frozen value. The caps are applied here: the dirty paths, the passing commands, the last `limit`
ledger lines, the review decisions and the failed attempts.
"""

from itertools import islice
from typing import TYPE_CHECKING

from mightymodels_core.contract.policy import ReceiptAssessment
from mightymodels_core.primitives import short_head
from mightymodels_core.snapshot.records import (
    CheckState,
    FailedAttempt,
    LedgerLine,
    PassingCommand,
    RepositoryState,
    ReviewDecision,
    ReviewState,
    TaskState,
    TicketSummary,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mightymodels_core.contract.records import Receipt, RecordedCommand
    from mightymodels_core.git import GitRefusal
    from mightymodels_core.investigations.ledger import Ledger, LinkedLedgers
    from mightymodels_core.reviews.services import LatestReview
    from mightymodels_core.snapshot.records import RepositoryFacts
    from mightymodels_core.tasks.records import AttemptCounts, TaskRecord, Transition
    from mightymodels_core.tickets.records import TicketRecord
    from mightymodels_core.vocabulary.investigations import EntryKind

NOT_STARTED = 'not started'
NEVER_RUN = 'never-run'


def git_warnings(refusal: GitRefusal | None) -> tuple[str, ...]:
    return () if refusal is None else (f'git was not consulted: {refusal}',)


def repository_state(facts: RepositoryFacts, limit: int) -> RepositoryState:
    dirty = facts.dirty
    return RepositoryState(
        branch=facts.branch,
        head=facts.head,
        dirty_count=None if dirty is None else len(dirty),
        dirty=() if dirty is None else dirty[:limit],
    )


def ticket_summary(ticket: TicketRecord) -> TicketSummary:
    section = ticket.section
    return TicketSummary(
        summary=section.summary,
        status=ticket.status,
        scope=section.scope,
        tracker=section.tracker,
    )


def task_state(record: TaskRecord, attempts: AttemptCounts) -> TaskState:
    return TaskState(
        task=record.key,
        status=NOT_STARTED if record.status == 'pending' else record.status,
        attempts=attempts.get(record.key, {}),
        reasons=record.reasons,
    )


def check_text(receipt: Receipt | None, head: str | None) -> str:
    if receipt is None:
        return NEVER_RUN

    if ReceiptAssessment(receipt=receipt, head=head).state == 'stale':
        return f'stale ({receipt.outcome} at {short_head(receipt.head)})'

    return receipt.outcome


def check_states(
    commands: Sequence[RecordedCommand], receipts: Mapping[str, Receipt], head: str | None
) -> tuple[CheckState, ...]:
    return tuple(
        CheckState(key=command.key, state=check_text(receipts.get(command.key), head))
        for command in commands
    )


def last_passed(command: RecordedCommand, receipts: Mapping[str, Receipt]) -> bool:
    receipt = receipts.get(command.key)
    return receipt is not None and receipt.outcome == 'pass'


def passing_commands(
    commands: Sequence[RecordedCommand], receipts: Mapping[str, Receipt], limit: int
) -> tuple[PassingCommand, ...]:
    passing = (
        PassingCommand(key=command.key, argv=command.argv)
        for command in commands
        if last_passed(command, receipts)
    )
    return tuple(islice(passing, limit))


def failed_attempts(stuck: Sequence[Transition]) -> tuple[FailedAttempt, ...]:
    return tuple(
        FailedAttempt(
            task=transition.task_key,
            to=transition.after,
            reason='; '.join(transition.reasons),
            head=short_head(transition.head),
            at=transition.at,
        )
        for transition in stuck
    )


def ledger_lines(ledgers: Sequence[Ledger], kind: EntryKind, limit: int) -> tuple[LedgerLine, ...]:
    lines = [
        LedgerLine(
            kind=record.kind, text=record.text, cite=record.cite, origin=ledger.origin_of(record)
        )
        for ledger in ledgers
        for record in ledger.live_of_kind(kind)
    ]
    if limit <= 0:
        return ()

    return tuple(lines[-limit:])


def ledger_warnings(linked: LinkedLedgers) -> tuple[str, ...]:
    return tuple(f'investigation {investigation} is missing' for investigation in linked.missing)


def review_state(review: LatestReview | None, limit: int) -> ReviewState | None:
    if review is None:
        return None

    run = review.run
    decisions = (
        ReviewDecision(
            finding=decided.finding_key, decision=decided.decision, reason=decided.reason
        )
        for decided in review.decided
        if decided.decision != review.options.chosen_decision
    )
    return ReviewState(
        run=run.run_id,
        depth=run.depth,
        head=short_head(run.head),
        findings=len(review.findings),
        undecided=review.undecided,
        remediation_open=review.open_remediation,
        decisions=tuple(islice(decisions, limit)),
    )
