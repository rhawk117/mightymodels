from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.git.revisions import revision_error
from mightymodels_core.primitives import RedactedTextTooLongError
from mightymodels_core.ticket_closing import (
    LIVE_DEBUG,
    NO_VERIFIED_WORK,
    ClosingOptions,
    ClosingPolicy,
    LiveWorkPolicy,
    ShippedRequiredError,
    TooManyGotchasError,
    create_one_lined_closing,
    get_moved_fields,
)
from mightymodels_core.tickets import TicketRecord

from .conftest import (
    SERVICE_BRANCH,
    SERVICE_SLUG,
    create_branch_facts,
    create_facts,
    create_latest_review,
    create_lines,
    create_task,
    create_ticket_section,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.reviews import LatestReview
    from mightymodels_core.schemas.reviews import Decision
    from mightymodels_core.schemas.tasks import TaskStatus
    from mightymodels_core.tasks import TaskRecord
    from mightymodels_core.ticket_closing import BranchFacts, CloseFacts

ASSIGNMENT_LINE = 'password=abcd'


@dataclass(slots=True, kw_only=True, frozen=True)
class BranchCase:
    name: str
    facts: CloseFacts
    expected: tuple[str, ...]
    branch: str = SERVICE_BRANCH
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


def facts_with_branch(branch: BranchFacts | None) -> CloseFacts:
    return replace(create_facts(), branch=branch)


def live_work_branch_cases() -> pytest.MarkDecorator:
    name = SERVICE_BRANCH
    cases = [
        BranchCase(name='clean', facts=create_facts(), expected=()),
        BranchCase(
            name='commits-on-no-remote',
            facts=facts_with_branch(create_branch_facts(unpushed=2)),
            expected=(f'branch {name} has 2 commits on no remote',),
        ),
        BranchCase(
            name='unpushed-count-unreadable',
            facts=facts_with_branch(create_branch_facts(unpushed=None)),
            expected=(
                f'branch {name} could not be checked: git could not count its commits on no remote',
            ),
        ),
        BranchCase(
            name='checked-out-with-uncommitted-changes',
            facts=facts_with_branch(create_branch_facts(checked_out=True, dirty=1)),
            expected=(f'branch {name} is checked out with uncommitted changes',),
        ),
        BranchCase(
            name='working-tree-status-unreadable',
            facts=facts_with_branch(create_branch_facts(checked_out=True, dirty=None)),
            expected=(
                f'branch {name} could not be checked: git could not read the working-tree status',
            ),
        ),
        BranchCase(
            name='dirty-but-not-checked-out',
            facts=facts_with_branch(create_branch_facts(checked_out=False, dirty=3)),
            expected=(),
        ),
        BranchCase(
            name='branch-no-longer-in-the-repository',
            facts=facts_with_branch(create_branch_facts(exists=False, unpushed=4)),
            expected=(),
        ),
        BranchCase(
            name='git-cannot-be-asked-about-the-branch',
            facts=facts_with_branch(None),
            expected=(f'branch {name} could not be checked: git could not be asked about it',),
        ),
        BranchCase(
            name='branch-name-fails-the-revision-check',
            branch='-bad',
            facts=create_facts(),
            expected=(f'branch -bad could not be checked: {revision_error("-bad")}',),
        ),
        BranchCase(
            name='git-was-not-consulted',
            facts=replace(
                facts_with_branch(create_branch_facts(unpushed=2)), git_refusal='no git binary'
            ),
            expected=(),
        ),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


def unverified_status_cases() -> pytest.MarkDecorator:
    statuses: list[TaskStatus] = ['in-progress', 'failed', 'blocked']
    return pytest.mark.parametrize(
        'status', [pytest.param(status, id=status) for status in statuses]
    )


VERIFIED = create_task('T1', 'verified')


def find_live_work(
    *,
    tasks: tuple[TaskRecord, ...] = (VERIFIED,),
    review: LatestReview | None = None,
    facts: CloseFacts | None = None,
    branch: str = SERVICE_BRANCH,
) -> list[str]:
    policy = LiveWorkPolicy(
        branch=branch, tasks=tasks, review=review, facts=facts or create_facts()
    )
    return policy.get_live_work_blockers()


class TestTaskBlockers:
    def test_a_verified_ticket_with_nothing_else_has_no_live_work(self) -> None:
        assert find_live_work() == []

    def test_no_recorded_task_means_no_verified_work(self) -> None:
        assert find_live_work(tasks=()) == [NO_VERIFIED_WORK]

    def test_a_task_never_started_is_named_before_the_missing_verified_work(self) -> None:
        blockers = find_live_work(tasks=(create_task('T1', 'pending'),))

        assert blockers == ['T1 has contract commands but was never started', NO_VERIFIED_WORK]

    @unverified_status_cases()
    def test_an_unverified_plan_task_blocks_closing(self, status: TaskStatus) -> None:
        started = create_task('T2', status)
        blockers = find_live_work(tasks=(VERIFIED, started))

        assert blockers == [f'T2 is {status}, not verified']

    def test_a_superseded_plan_task_blocks_nothing(self) -> None:
        superseded = create_task('T2', 'superseded')

        assert find_live_work(tasks=(VERIFIED, superseded)) == []

    def test_a_blocked_residual_task_blocks_closing(self) -> None:
        residual = create_task('R1', 'blocked')

        assert find_live_work(tasks=(VERIFIED, residual)) == ['R1 is blocked, not verified']


class TestFactBlockers:
    def test_a_live_debug_note_blocks_closing(self) -> None:
        assert find_live_work(facts=create_facts(debug_note=True)) == [LIVE_DEBUG]

    @live_work_branch_cases()
    def test_branch_blockers(self, case: BranchCase) -> None:
        blockers = find_live_work(facts=case.facts, branch=case.branch)

        assert blockers == list(case.expected)


class TestReviewBlockers:
    def test_an_undecided_finding_blocks_closing(self) -> None:
        review = create_latest_review({'F1': 'dismiss'}, undecided=('F2',))

        assert find_live_work(review=review) == ['review finding F2 has no decision']

    def test_a_finding_chosen_for_fixing_and_not_fixed_blocks_closing(self) -> None:
        review = create_latest_review({'F1': 'fix'})

        assert find_live_work(review=review) == [
            'review finding F1 was chosen for fixing and is not fixed'
        ]

    def test_decided_findings_fixed_deferred_or_dismissed_block_nothing(self) -> None:
        decided: dict[str, Decision] = {
            'F1': 'fix',
            'F2': 'defer',
            'F3': 'dismiss',
            'F4': 'accept-risk',
        }
        review = create_latest_review(decided, fixed=('F1',))

        assert find_live_work(review=review) == []


class TestClosingPolicy:
    options = ClosingOptions(gotcha_limit=3, line_limit=15)

    def find_problem(self, shipped: str, gotchas: tuple[str, ...]) -> Exception | None:
        lines = create_lines(shipped, gotchas)
        closing = create_one_lined_closing(lines, ClosingOptions())
        return ClosingPolicy(closing=closing, options=self.options).get_closing_problem()

    def test_a_blank_shipped_line_is_refused(self) -> None:
        assert isinstance(self.find_problem('  \n ', ()), ShippedRequiredError)

    def test_three_gotchas_are_held_and_a_fourth_is_refused(self) -> None:
        held = self.find_problem('shipped', ('a', 'b', 'c'))
        refused = self.find_problem('shipped', ('a', 'b', 'c', 'd'))

        assert held is None
        assert isinstance(refused, TooManyGotchasError)
        assert (refused.given, refused.limit) == (4, 3)

    def test_blank_gotchas_do_not_count_toward_the_limit(self) -> None:
        assert self.find_problem('shipped', ('a', '', ' ', 'b', 'c')) is None


class TestOneLinedClosing:
    def test_each_line_is_one_line_with_its_whitespace_collapsed(self) -> None:
        lines = create_lines('shipped   the\n service', ('a\n  gotcha',))

        closing = create_one_lined_closing(lines, ClosingOptions())

        assert closing.shipped == 'shipped the service'
        assert closing.gotchas == ('a gotcha',)

    def test_a_secret_is_redacted_from_every_line(self) -> None:
        closing = create_one_lined_closing(create_lines(ASSIGNMENT_LINE), ClosingOptions())

        assert 'abcd' not in closing.shipped

    def test_a_blank_pr_is_none(self) -> None:
        lines = replace(create_lines(), pr='  ')

        assert create_one_lined_closing(lines, ClosingOptions()).pr is None

    def test_a_line_that_redaction_lengthens_past_its_limit_is_refused(self) -> None:
        options = ClosingOptions(line_limit=len(ASSIGNMENT_LINE))

        with pytest.raises(RedactedTextTooLongError):
            create_one_lined_closing(create_lines(ASSIGNMENT_LINE), options)


class TestMovedFields:
    seen = TicketRecord(
        id=1,
        slug=SERVICE_SLUG,
        status='staged',
        section=create_ticket_section(),
        investigations=('probe',),
    )

    def test_an_unchanged_ticket_has_moved_nothing(self) -> None:
        assert get_moved_fields(self.seen, replace(self.seen)) == []

    def test_each_moved_field_is_named(self) -> None:
        section = replace(self.seen.section, branch='feat/other')
        current = replace(self.seen, status='in-progress', section=section, investigations=())

        assert get_moved_fields(self.seen, current) == ['status', 'branch', 'investigations']
