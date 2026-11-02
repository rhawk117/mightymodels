"""The readiness gate of the task domain, and the git facts a verification reports.

A ticket is ready only when a plan task has been started, every plan task is closed and no fix is
stuck. A verification is a verdict the primary records; the git facts beside it (HEAD, whether the
base is an ancestor, the files changed) are reported, never judged.

The caller passes the git facts in as values; the gate calls no git, reads no file and returns its
problems as the lines the caller shows, an empty list being a pass.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import TaskId
    from mightymodels_core.tasks.records import TaskRecord
    from mightymodels_core.tasks.services import VerifyRequest
    from mightymodels_core.vocabulary.tasks import TaskStatus

STUCK: frozenset[TaskStatus] = frozenset({'failed', 'blocked'})
CLOSED: frozenset[TaskStatus] = frozenset({'verified', 'superseded'})
PLAN_TASK_PREFIX = 'T'

type BaseStatus = Literal['ancestor', 'not-ancestor', 'unresolved']


def is_plan_task(task_key: TaskId) -> bool:
    return task_key.startswith(PLAN_TASK_PREFIX)


@dataclass(slots=True, kw_only=True, frozen=True)
class GitFacts:
    head: str | None
    base_resolves: bool
    base_is_ancestor: bool
    changed_files: frozenset[str]


@dataclass(slots=True, kw_only=True, frozen=True)
class VerifyFacts:
    commit_is_head: bool
    base_status: BaseStatus
    outside_owned: tuple[str, ...]


def get_base_status(git: GitFacts) -> BaseStatus:
    if not git.base_resolves:
        return 'unresolved'

    return 'ancestor' if git.base_is_ancestor else 'not-ancestor'


def get_verify_facts(request: VerifyRequest, record: TaskRecord) -> VerifyFacts:
    git = request.git
    return VerifyFacts(
        commit_is_head=request.commit == git.head,
        base_status=get_base_status(git),
        outside_owned=tuple(sorted(git.changed_files - set(record.owned))),
    )


def get_plan_task_problem(record: TaskRecord) -> str | None:
    if record.status == 'pending':
        return f'{record.key} was never started'

    if record.status in CLOSED:
        return None

    return f'{record.key} is {record.status}, not verified'


def get_readiness_problems(records: Sequence[TaskRecord]) -> list[str]:
    planned = [record for record in records if is_plan_task(record.key)]
    unproven = (get_plan_task_problem(record) for record in planned)
    return [
        *([] if planned else ['no plan task has been started']),
        *(problem for problem in unproven if problem is not None),
        *(
            f'{record.key} is {record.status}: {"; ".join(record.reasons)}'
            for record in records
            if not is_plan_task(record.key) and record.status in STUCK
        ),
    ]
