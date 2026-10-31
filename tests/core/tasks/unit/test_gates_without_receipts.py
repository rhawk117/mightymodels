"""Task verification proves criteria by citation alone, never by receipts or contract commands."""

from dataclasses import replace

from mightymodels_core.tasks import Brief, Evidence, TaskRecord, VerificationGate

from tests.core.tasks.service_builders import (
    BASE_COMMIT,
    DONE_COMMIT,
    FIRST_TASK,
    OWNED_FILE,
    create_git_facts,
)

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

    def test_evidence_carries_no_commands_or_receipts(self) -> None:
        evidence = create_gate(CITED).evidence

        assert not hasattr(evidence, 'commands')
        assert not hasattr(evidence, 'receipts')
        assert replace(evidence, assertions={}).assertions == {}
