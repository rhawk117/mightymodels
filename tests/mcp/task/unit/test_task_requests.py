from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest
from mightymodels_mcp.server.requests import NAME_LIMIT, PROSE_LIMIT
from mightymodels_mcp.task.schemas import (
    TaskMarkRequest,
    TaskStartRequest,
    TaskVerifyRequest,
    create_mark_request,
    create_start_request,
)
from pydantic import ValidationError

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

START = MappingProxyType({
    'slug': 'probe-ticket',
    'task_id': 'T20',
    'by': 'engineer',
    'owned': ('src/a.py',),
    'acceptance': ('AC-1: it passes',),
})
VERIFY = MappingProxyType({'slug': 'probe-ticket', 'task_id': 'T20', 'commit': 'HEAD'})
MARK = MappingProxyType({
    'slug': 'probe-ticket',
    'task_id': 'T20',
    'to': 'blocked',
    'reason': 'the plan is wrong',
})


def create_start(**given: Any) -> TaskStartRequest:
    return TaskStartRequest.model_validate({**START, **given})


def create_verify(**given: Any) -> TaskVerifyRequest:
    return TaskVerifyRequest.model_validate({**VERIFY, **given})


def create_mark(**given: Any) -> TaskMarkRequest:
    return TaskMarkRequest.model_validate({**MARK, **given})


def invalid_start_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param({'task_id': 'X1'}, id='task-id-prefix'),
        pytest.param({'task_id': 'T1234567'}, id='task-id-too-long'),
        pytest.param({'by': 'wizard'}, id='worker'),
        pytest.param({'owned': ()}, id='no-owned'),
        pytest.param({'acceptance': ()}, id='no-acceptance'),
        pytest.param({'owned': ('x' * (PROSE_LIMIT + 1),)}, id='owned-oversized'),
        pytest.param({'acceptance': ('x' * (NAME_LIMIT + 1),)}, id='criterion-oversized'),
        pytest.param({'mode': 'improvise'}, id='mode'),
        pytest.param({'too_large_approved_by': 'robot'}, id='approver'),
        pytest.param({'slug': 'Not A Slug'}, id='slug'),
        pytest.param({'unknown': 'field'}, id='extra-field'),
    ]
    return pytest.mark.parametrize('change', cases)


class TestTaskStartRequest:
    @invalid_start_cases()
    def test_invalid_field_is_refused(self, change: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            create_start(**change)

    def test_more_than_core_allows_is_left_to_core(self) -> None:
        request = create_start(owned=tuple(f'f{n}.py' for n in range(11)), acceptance=('a',) * 5)

        assert len(request.owned) == 11

    def test_start_request_counts_the_criteria(self) -> None:
        request = create_start(acceptance=('a', 'b', 'c'), mode='diagnose-replan')

        started = create_start_request(request, 'abc123')

        assert (started.task_key, started.worker, started.mode) == (
            'T20',
            'engineer',
            'diagnose-replan',
        )
        assert (started.owned, started.acceptance_count, started.head) == (
            ('src/a.py',),
            3,
            'abc123',
        )
        assert not started.too_large_approved

    def test_start_request_is_approved_only_when_the_user_is_named(self) -> None:
        started = create_start_request(create_start(too_large_approved_by='user'), None)

        assert started.too_large_approved
        assert started.head is None


class TestTaskVerifyRequest:
    def test_leading_dash_commit_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            create_verify(commit='--output=x')

    def test_commit_over_the_name_limit_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            create_verify(commit='a' * (NAME_LIMIT + 1))

    def test_assertions_default_to_none(self) -> None:
        assert create_verify().assertions == {}

    def test_assertion_over_the_prose_limit_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            create_verify(assertions={'AC-1': 'x' * (PROSE_LIMIT + 1)})


class TestTaskMarkRequest:
    def test_verified_is_not_a_mark(self) -> None:
        with pytest.raises(ValidationError):
            create_mark(to='verified')

    def test_mark_request_carries_the_task_and_reason(self) -> None:
        marked = create_mark_request(create_mark())

        assert (marked.task_key, marked.to, marked.reason) == (
            'T20',
            'blocked',
            'the plan is wrong',
        )
