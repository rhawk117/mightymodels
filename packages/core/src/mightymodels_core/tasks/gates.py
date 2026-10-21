"""The two gates of the task domain: what keeps a task from verified and a ticket from ready.

A task is proven only when the reported commit is the current HEAD and descends from the task's
base, every contract command for it passed at that HEAD, its DONE brief names the commit, every
other acceptance criterion carries a citation, and the commit touched only the files the task
owns. A ticket is ready only when a plan task has been started, every plan task is closed and no
fix is stuck.

The caller passes the git facts and the brief text in as values; the gates call no git, read no
file and return their problems as the lines the caller shows, an empty list being a pass.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mightymodels_core.contract.records import Receipt, RecordedCommand
    from mightymodels_core.primitives import TaskId
    from mightymodels_core.schemas.tasks import TaskStatus
    from mightymodels_core.tasks.records import TaskRecord

DONE_HEADING = '## DONE'
ASKED_CRITERION = re.compile(r'^\s*-\s*(AC-\d+)\s*:', re.MULTILINE)
DONE_COMMIT = re.compile(r'^\s*commit:\s*([0-9a-fA-F]{7,64})\s*$', re.MULTILINE)
STUCK: frozenset[TaskStatus] = frozenset({'failed', 'blocked'})
CLOSED: frozenset[TaskStatus] = frozenset({'verified', 'superseded'})
PLAN_TASK_PREFIX = 'T'


def is_plan_task(task_key: TaskId) -> bool:
    return task_key.startswith(PLAN_TASK_PREFIX)


def done_commit(brief_text: str) -> str | None:
    _, separator, done = brief_text.partition(DONE_HEADING)
    named = DONE_COMMIT.search(done)
    return str(named[1]) if separator and named else None


def criteria_in_brief(brief_text: str) -> list[str]:
    asked = brief_text.split(DONE_HEADING, 1)[0]
    return [found[1] for found in ASKED_CRITERION.finditer(asked)]


@dataclass(slots=True, kw_only=True, frozen=True)
class GitFacts:
    head: str | None
    base_resolves: bool
    base_is_ancestor: bool
    changed_files: frozenset[str]
    named_commit: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Brief:
    text: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Evidence:
    commit: str
    brief: Brief | None
    assertions: Mapping[str, str]
    commands: Sequence[RecordedCommand]
    receipts: Mapping[str, Receipt]


def get_receipt_problem(command_key: str, receipt: Receipt | None, head: str | None) -> str | None:
    if receipt is None or head is None or receipt.head != head:
        return f'{command_key} has no receipt at the current HEAD'

    if receipt.outcome != 'pass':
        return f'{command_key} {receipt.outcome} at HEAD'

    return None


def get_receipt_problems(
    commands: Sequence[RecordedCommand], receipts: Mapping[str, Receipt], head: str | None
) -> list[str]:
    problems = (
        get_receipt_problem(command.key, receipts.get(command.key), head) for command in commands
    )
    return [problem for problem in problems if problem is not None]


@dataclass(slots=True, kw_only=True, frozen=True)
class VerificationGate:
    task: TaskRecord
    evidence: Evidence
    git: GitFacts

    @property
    def brief_text(self) -> str | None:
        brief = self.evidence.brief
        return None if brief is None else brief.text

    @property
    def proven_criteria(self) -> set[str]:
        by_command = {command.key.split('.', 1)[1] for command in self.evidence.commands}
        return by_command | set(self.evidence.assertions)

    def commit_problems(self) -> list[str]:
        if self.evidence.commit != self.git.head:
            return ['the reported commit must resolve to the current HEAD']

        if self.task.base is None or not self.git.base_resolves:
            return ['the task has no valid base commit']

        if not self.git.base_is_ancestor:
            return ['the task base is not an ancestor of the reported commit']

        return []

    def receipt_problems(self) -> list[str]:
        return get_receipt_problems(self.evidence.commands, self.evidence.receipts, self.git.head)

    def brief_problems(self) -> list[str]:
        if self.evidence.brief is None:
            return []

        if self.brief_text is None:
            return ['the task brief is missing']

        if self.git.named_commit != self.evidence.commit:
            return ['the DONE brief must name the reported HEAD commit']

        return []

    def criteria_problems(self) -> list[str]:
        asked = criteria_in_brief(self.brief_text or '')
        proven = self.proven_criteria
        problems = [
            f'{criterion} has neither a contract command nor a citation'
            for criterion in asked
            if criterion not in proven
        ]
        if not proven:
            problems.append('no contract command and no cited assertion proves this task')

        return problems

    def ownership_problems(self) -> list[str]:
        outside = sorted(self.git.changed_files - set(self.task.owned))
        return [f'changed outside the owned set: {path}' for path in outside]

    def get_verification_problems(self) -> list[str]:
        if problems := self.commit_problems():
            return problems

        return [
            *self.receipt_problems(),
            *self.brief_problems(),
            *self.criteria_problems(),
            *self.ownership_problems(),
        ]


def get_plan_task_problem(record: TaskRecord) -> str | None:
    if record.status == 'pending':
        return f'{record.key} has contract commands but was never started'

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
