from typing import TYPE_CHECKING

import pytest
from mightymodels_hooks.completion_gate import unfinished_reason
from mightymodels_hooks.completion_state import Unfinished

from tests.hooks.completion_gate.completion_gate_builders import (
    ASKED_ONLY,
    BASE,
    DONE_WITH_A_COMMIT,
    DONE_WITHOUT_A_COMMIT,
    HEAD,
    OUTSIDE,
    plan_task,
    residual_facts,
)

if TYPE_CHECKING:
    from mightymodels_hooks.completion_state import ResidualFacts

SLUG = 'port-it'


def plan_task_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('text', 'lack'),
        [
            pytest.param(None, 'task-01.md is missing', id='no-brief'),
            pytest.param(ASKED_ONLY, 'has no DONE half naming a commit', id='no-done-half'),
            pytest.param(
                DONE_WITHOUT_A_COMMIT, 'has no DONE half naming a commit', id='no-commit-line'
            ),
        ],
    )


def residual_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('facts', 'lack'),
        [
            pytest.param(residual_facts(head=None), 'no commit follows its base', id='no-head'),
            pytest.param(residual_facts(head=BASE), 'no commit follows its base', id='at-base'),
            pytest.param(
                residual_facts(resolves=False), 'the task has no valid base commit', id='bad-base'
            ),
            pytest.param(
                residual_facts(changed=frozenset({OUTSIDE})),
                f'changed outside the owned set: {OUTSIDE}',
                id='outside-the-owned-set',
            ),
        ],
    )


class TestUnfinishedReason:
    @plan_task_cases()
    def test_a_plan_task_is_named_with_what_its_brief_lacks(
        self, text: str | None, lack: str
    ) -> None:
        reason = unfinished_reason(
            Unfinished(slug=SLUG, plan_tasks=[plan_task(text)], residuals=[])
        )
        assert reason is not None
        assert f'ticket {SLUG}: T1 is in progress and its brief' in reason
        assert lack in reason
        assert 'Append the `## DONE` half' in reason

    def test_a_brief_naming_a_commit_is_not_held(self) -> None:
        unfinished = Unfinished(slug=SLUG, plan_tasks=[plan_task(DONE_WITH_A_COMMIT)], residuals=[])
        assert unfinished_reason(unfinished) is None

    @residual_cases()
    def test_a_residual_is_named_with_what_it_lacks_and_no_brief(
        self, facts: ResidualFacts, lack: str
    ) -> None:
        unfinished = Unfinished(slug=SLUG, plan_tasks=[], residuals=[facts])
        reason = unfinished_reason(unfinished)
        assert reason is not None
        assert f'R1 is in progress and {lack}' in reason
        assert f'mightymodels verify run --slug {SLUG} --id' in reason
        assert 'brief' not in reason

    def test_a_residual_that_follows_its_base_inside_its_files_is_not_held(self) -> None:
        unfinished = Unfinished(slug=SLUG, plan_tasks=[], residuals=[residual_facts(head=HEAD)])
        assert unfinished_reason(unfinished) is None

    def test_nothing_started_is_not_held(self) -> None:
        assert unfinished_reason(Unfinished(slug=SLUG, plan_tasks=[], residuals=[])) is None
