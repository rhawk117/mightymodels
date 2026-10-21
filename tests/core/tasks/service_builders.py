"""Builders and shared values for the task service tests."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mightymodels_core.contract.records import ApprovedCommand, Receipt
from mightymodels_core.primitives import Slug, TaskId, redact
from mightymodels_core.tasks import Brief, GitFacts, StartRequest, VerifyRequest

if TYPE_CHECKING:
    from mightymodels_core.schemas.tasks import ArchitectMode, Worker
    from mightymodels_core.tasks import TaskRecord

    from .conftest import ServiceHarness

FIRST_TASK = TaskId('T1')
SERVICE_SLUG = Slug('service-subject')
OTHER_SLUG = Slug('unstaged-subject')
SERVICE_MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
BASE_COMMIT = 'base001'
DONE_COMMIT = 'abc1234'
OWNED_FILE = 'src/a.py'
BRIEF_TEXT = f'## ASKED\nacceptance:\n  - AC-1: it works\n## DONE\ncommit: {DONE_COMMIT}\n'


def create_start_request(
    *,
    task_key: TaskId = FIRST_TASK,
    worker: Worker = 'engineer',
    mode: ArchitectMode | None = None,
    owned: tuple[str, ...] = (OWNED_FILE,),
    acceptance_count: int = 1,
) -> StartRequest:
    return StartRequest(
        task_key=task_key,
        worker=worker,
        mode=mode,
        owned=owned,
        acceptance_count=acceptance_count,
        head=BASE_COMMIT,
    )


def create_git_facts(*, changed_files: frozenset[str] = frozenset({OWNED_FILE})) -> GitFacts:
    return GitFacts(
        head=DONE_COMMIT,
        base_resolves=True,
        base_is_ancestor=True,
        changed_files=changed_files,
        named_commit=DONE_COMMIT,
    )


def create_verify_request(seen: TaskRecord, *, changed_files: frozenset[str]) -> VerifyRequest:
    return VerifyRequest(
        seen=seen,
        commit=DONE_COMMIT,
        assertions={},
        git=create_git_facts(changed_files=changed_files),
        brief=Brief(text=BRIEF_TEXT),
    )


def verify_as_asked(harness: ServiceHarness, changed_files: frozenset[str]) -> TaskRecord:
    seen = harness.service.prepare_verification(SERVICE_SLUG, FIRST_TASK)
    request = create_verify_request(seen, changed_files=changed_files)
    return harness.service.verify(SERVICE_SLUG, request)


def create_receipt(key: str, *, head: str = DONE_COMMIT) -> Receipt:
    return Receipt(
        key=key,
        argv=('true',),
        outcome='pass',
        exit=0,
        duration_ms=1,
        stdout_tail=redact(''),
        stderr_tail=redact(''),
        digest='digest',
        head=head,
        phase='task',
        at=SERVICE_MOMENT,
    )


def create_command(key: str) -> ApprovedCommand:
    return ApprovedCommand(
        key=key, argv=('true',), expect_exit=0, timeout=10, approved_by='the user'
    )
