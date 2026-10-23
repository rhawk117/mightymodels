from dataclasses import replace
from typing import TYPE_CHECKING

from mightymodels_core.contract.records import Receipt, RecordedCommand
from mightymodels_core.investigations import InvestigationRecord, Ledger, LedgerRecord
from mightymodels_core.primitives import Slug, TaskId, redact
from mightymodels_core.ticket_closing import (
    ArchivedCommand,
    ArchivedDecision,
    archived_command,
    archived_decisions,
    archived_review,
)

from tests.core.ticket_closing.conftest import REVIEW_RUN, SERVICE_MOMENT, create_latest_review

if TYPE_CHECKING:
    from mightymodels_core.schemas.investigations import EntryKind
    from mightymodels_core.schemas.reviews import Decision

FIRST = Slug('first-probe')
SECOND = Slug('second-probe')
COMMAND = RecordedCommand(
    key='T1.AC-1', task_key=TaskId('T1'), argv=('true',), expect_exit=0, timeout=10
)


def create_entry(seq: int, text: str, *, kind: EntryKind = 'decision') -> LedgerRecord:
    return LedgerRecord(
        seq=seq,
        round=1,
        kind=kind,
        text=redact(text),
        source='code-scout',
        cite=None,
        supersedes=(),
        at=SERVICE_MOMENT,
        head='abc1234',
    )


def create_ledger(key: Slug, *records: LedgerRecord) -> Ledger:
    investigation = InvestigationRecord(key=key, target=redact('a target'), kind='behavior')
    return Ledger(investigation=investigation, records=records)


def create_receipt() -> Receipt:
    return Receipt(
        key=COMMAND.key,
        argv=COMMAND.argv,
        outcome='fail',
        exit=1,
        duration_ms=1,
        stdout_tail=redact(''),
        stderr_tail=redact(''),
        digest='digest1',
        head='abc1234',
        phase='task',
        at=SERVICE_MOMENT,
    )


class TestArchivedCommand:
    def test_a_command_with_no_receipt_is_never_run(self) -> None:
        assert archived_command(COMMAND, None) == ArchivedCommand(
            key='T1.AC-1',
            argv=('true',),
            expect_exit=0,
            outcome='never-run',
            head=None,
            digest=None,
        )

    def test_a_command_with_a_receipt_carries_its_outcome_head_and_digest(self) -> None:
        archived = archived_command(COMMAND, create_receipt())

        assert (archived.outcome, archived.head, archived.digest) == ('fail', 'abc1234', 'digest1')


class TestArchivedReview:
    def test_a_ticket_with_no_review_archives_none(self) -> None:
        assert archived_review(None) is None

    def test_findings_are_grouped_by_decision_with_fixed_told_apart(self) -> None:
        decided: dict[str, Decision] = {'F1': 'fix', 'F2': 'dismiss', 'F3': 'fix'}
        review = create_latest_review(decided, undecided=('F4',), fixed=('F1',))

        archived = archived_review(review)

        assert archived is not None
        assert archived.run == REVIEW_RUN
        assert archived.findings == 4
        assert archived.by_decision == {'fixed': ('F1',), 'dismiss': ('F2',), 'fix': ('F3',)}

    def test_each_reason_is_one_line(self) -> None:
        archived = archived_review(create_latest_review({'F1': 'dismiss'}))

        assert archived is not None
        assert archived.reasons == {'F1': 'worth doing'}


class TestArchivedDecisions:
    def test_live_decisions_of_every_ledger_carry_their_origin(self) -> None:
        first = create_ledger(
            FIRST, create_entry(1, 'use a policy'), create_entry(2, 'a fact', kind='known')
        )
        second = create_ledger(SECOND, create_entry(1, 'keep   it\n sync'))

        assert archived_decisions([first, second], 4) == (
            ArchivedDecision(text=redact('use a policy'), origin='first-probe e1'),
            ArchivedDecision(text=redact('keep it sync'), origin='second-probe e1'),
        )

    def test_a_superseded_decision_is_left_out(self) -> None:
        retired = create_entry(1, 'old choice')
        current = replace(create_entry(2, 'new choice'), supersedes=(1,))

        decisions = archived_decisions([create_ledger(FIRST, retired, current)], 4)

        assert [decision.text for decision in decisions] == ['new choice']

    def test_only_the_latest_decisions_up_to_the_limit_are_kept(self) -> None:
        entries = [create_entry(seq, f'choice {seq}') for seq in range(1, 6)]

        decisions = archived_decisions([create_ledger(FIRST, *entries)], 2)

        assert [decision.text for decision in decisions] == ['choice 4', 'choice 5']
