"""Every rule a close is refused by, computed from values passed in.

The caller reads the ticket, its tasks and its latest review, asks git, and passes what it found.
`LiveWorkPolicy` lists what a closed ticket would strand; `ClosingPolicy` checks the closing lines
once they are one line each. A policy reads no repository, no clock, no git and no disk.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.git.revisions import revision_error
from mightymodels_core.primitives import redact_within
from mightymodels_core.tasks.gates import get_plan_task_problem, is_plan_task
from mightymodels_core.ticket_closing.errors import ShippedRequiredError, TooManyGotchasError
from mightymodels_core.ticket_closing.records import OneLinedClosing

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.reviews.services import LatestReview
    from mightymodels_core.tasks.records import TaskRecord
    from mightymodels_core.ticket_closing.records import BranchFacts, CloseFacts, ClosingLines
    from mightymodels_core.tickets.records import TicketRecord

NO_VERIFIED_WORK = 'no verified task work is recorded'
LIVE_DEBUG = 'the live debug note is present: a debug is still live'


@dataclass(slots=True, kw_only=True, frozen=True)
class ClosingOptions:
    gotcha_limit: int = 3
    line_limit: int = 4000
    decision_limit: int = 4


def get_moved_fields(seen: TicketRecord, current: TicketRecord) -> list[str]:
    moved = {
        'status': seen.status != current.status,
        'branch': seen.section.branch != current.section.branch,
        'investigations': seen.investigations != current.investigations,
    }
    return [field_name for field_name, changed in moved.items() if changed]


def unchecked(branch: str, reason: str) -> str:
    return f'branch {branch} could not be checked: {reason}'


def one_line(text: str) -> str:
    return ' '.join(text.split())


def create_one_lined_closing(lines: ClosingLines, options: ClosingOptions) -> OneLinedClosing:
    limit = options.line_limit
    pr_line = one_line(lines.pr or '')
    pr = redact_within(pr_line, 'pr', limit) if pr_line else None
    return OneLinedClosing(
        shipped=redact_within(one_line(lines.shipped), 'shipped', limit),
        pr=pr,
        gotchas=tuple(
            redact_within(one_line(gotcha), 'gotchas', limit)
            for gotcha in lines.gotchas
            if gotcha.strip()
        ),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class LiveWorkPolicy:
    branch: str
    tasks: Sequence[TaskRecord]
    review: LatestReview | None
    facts: CloseFacts

    @property
    def planned(self) -> list[TaskRecord]:
        return [task for task in self.tasks if is_plan_task(task.key)]

    def get_task_blockers(self) -> list[str]:
        never_started = [task for task in self.planned if task.status == 'pending']
        started = [task for task in self.planned if task.status != 'pending']
        return [
            *problems_of(never_started),
            *([] if started else [NO_VERIFIED_WORK]),
            *problems_of(started),
        ]

    def get_debug_blockers(self) -> list[str]:
        return [LIVE_DEBUG] if self.facts.debug_note else []

    def get_review_blockers(self) -> list[str]:
        if self.review is None:
            return []

        return [
            *(f'review finding {key} has no decision' for key in self.review.undecided),
            *(
                f'review finding {key} was chosen for fixing and is not fixed'
                for key in self.review.open_remediation
            ),
        ]

    def get_unpushed_blockers(self, branch: BranchFacts) -> list[str]:
        if branch.unpushed is None:
            return [unchecked(self.branch, 'git could not count its commits on no remote')]

        if branch.unpushed > 0:
            return [f'branch {self.branch} has {branch.unpushed} commits on no remote']

        return []

    def get_uncommitted_blockers(self, branch: BranchFacts) -> list[str]:
        if not branch.checked_out:
            return []

        if branch.dirty is None:
            return [unchecked(self.branch, 'git could not read the working-tree status')]

        if branch.dirty > 0:
            return [f'branch {self.branch} is checked out with uncommitted changes']

        return []

    def get_branch_blockers(self) -> list[str]:
        if self.facts.git_refusal is not None:
            return []

        if (error := revision_error(self.branch)) is not None:
            return [unchecked(self.branch, str(error))]

        branch = self.facts.branch
        if branch is None:
            return [unchecked(self.branch, 'git could not be asked about it')]

        if not branch.exists:
            return []

        return [*self.get_unpushed_blockers(branch), *self.get_uncommitted_blockers(branch)]

    def get_live_work_blockers(self) -> list[str]:
        return [
            *self.get_task_blockers(),
            *self.get_debug_blockers(),
            *self.get_review_blockers(),
            *self.get_branch_blockers(),
        ]


def problems_of(tasks: Sequence[TaskRecord]) -> list[str]:
    problems = (get_plan_task_problem(task) for task in tasks)
    return [problem for problem in problems if problem is not None]


@dataclass(slots=True, kw_only=True, frozen=True)
class ClosingPolicy:
    closing: OneLinedClosing
    options: ClosingOptions = field(default_factory=ClosingOptions)

    def get_closing_problem(self) -> ShippedRequiredError | TooManyGotchasError | None:
        if not self.closing.shipped:
            return ShippedRequiredError()

        if len(self.closing.gotchas) > self.options.gotcha_limit:
            return TooManyGotchasError(
                given=len(self.closing.gotchas), limit=self.options.gotcha_limit
            )

        return None
