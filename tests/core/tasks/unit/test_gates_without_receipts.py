"""Task verification proves criteria by citation alone, never by receipts or contract commands."""

from typing import TYPE_CHECKING

from mightymodels_core.tasks import Brief, Evidence, TaskRecord, VerificationGate

from tests.core.tasks.service_builders import (
    BASE_COMMIT,
    DONE_COMMIT,
    FIRST_TASK,
    OWNED_FILE,
    create_git_facts,
    verify_as_asked,
)

if TYPE_CHECKING:
    from tests.core.tasks.service_builders import ServiceHarness

BRIEF = f'## ASKED\n  - AC-1: first\n  - AC-2: second\n## DONE\ncommit: {DONE_COMMIT}\n'
CITED = {'AC-1': f'{OWNED_FILE}:1', 'AC-2': f'{OWNED_FILE}:2'}


def create_gate(assertions: dict[str, str]) -> VerificationGate:
    task = TaskRecord(key=FIRST_TASK, status='in-progress', owned=(OWNED_FILE,), base=BASE_COMMIT)
    evidence = Evidence(commit=DONE_COMMIT, brief=Brief(text=BRIEF), assertions=assertions)
    return VerificationGate(task=task, evidence=evidence, git=create_git_facts())


class TestGatesWithoutReceipts:
    def test_a_task_with_every_criterion_cited_verifies_without_a_receipt(self) -> None:
        assert create_gate(CITED).get_verification_problems() == []

    def test_a_task_with_an_uncited_criterion_is_refused_naming_it(self) -> None:
        gate = create_gate({'AC-1': CITED['AC-1']})

        assert gate.get_verification_problems() == ['AC-2 has no citation']

    def test_a_task_with_nothing_cited_is_refused(self) -> None:
        gate = create_gate({})

        assert gate.get_verification_problems() == [
            'AC-1 has no citation',
            'AC-2 has no citation',
            'no cited assertion proves this task',
        ]

    def test_a_live_contract_command_with_no_receipt_still_verifies(
        self, contracted_harness: ServiceHarness
    ) -> None:
        record = verify_as_asked(contracted_harness, frozenset({OWNED_FILE}))

        assert (record.status, record.reasons) == ('verified', ())
