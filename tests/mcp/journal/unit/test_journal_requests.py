from typing import TYPE_CHECKING, Any

import pytest
from mightymodels_mcp.journal.schemas import (
    CrashoutAddRequest,
    CrashoutLastRequest,
    CrashoutStatsRequest,
    SimilaritySearchRequest,
)
from mightymodels_mcp.server.requests import NAME_LIMIT, PROSE_LIMIT
from pydantic import ValidationError

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

ENTRY: dict[str, Any] = {
    'severity': 'heated',
    'verdict': 'split',
    'rant': 'it broke',
    'failures': ['a failure'],
    'root_cause': 'a cause',
    'corrective_action': 'an action',
    'barked_back': False,
}


def add_request_refused_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param({'severity': 'mild'}, id='severity'),
        pytest.param({'verdict': 'guilty'}, id='verdict'),
        pytest.param({'ticket': '../escape'}, id='path-ticket'),
        pytest.param({'ticket': 'Not A Slug'}, id='slug'),
        pytest.param({'branch': 'x' * (NAME_LIMIT + 1)}, id='long-branch'),
        pytest.param({'rant': 'x' * (PROSE_LIMIT + 1)}, id='long-rant'),
        pytest.param({'failures': ['x' * (PROSE_LIMIT + 1)]}, id='long-failure'),
        pytest.param({'root_cause': 'x' * (PROSE_LIMIT + 1)}, id='long-root-cause'),
        pytest.param({'corrective_action': 'x' * (PROSE_LIMIT + 1)}, id='long-action'),
        pytest.param({'barked_back': 'maybe'}, id='barked-back'),
        pytest.param({'unknown': 1}, id='extra'),
        pytest.param({'entry': ENTRY}, id='nested-entry'),
        pytest.param({'action': 'add'}, id='action'),
    ]
    return pytest.mark.parametrize('change', cases)


def search_request_refused_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param({}, id='no-query'),
        pytest.param({'query': 'q', 'kind': 'galaxy'}, id='kind'),
        pytest.param({'query': 'x' * (PROSE_LIMIT + 1)}, id='long-query'),
        pytest.param({'query': 'q', 'unknown': 1}, id='extra'),
    ]
    return pytest.mark.parametrize('given', cases)


class TestCrashoutAddRequest:
    def test_optional_fields_default_to_none(self) -> None:
        request = CrashoutAddRequest.model_validate(ENTRY)

        assert (request.ticket, request.branch) == (None, None)
        assert request.failures == ('a failure',)
        assert request.barked_back is False

    def test_every_field_is_taken(self) -> None:
        request = CrashoutAddRequest.model_validate({
            **ENTRY,
            'ticket': 'probe-ticket',
            'branch': 'feat/probe',
            'barked_back': True,
        })

        assert (request.ticket, request.branch) == ('probe-ticket', 'feat/probe')
        assert (request.severity, request.verdict, request.barked_back) == ('heated', 'split', True)

    @add_request_refused_cases()
    def test_invalid_add_is_refused(self, change: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            CrashoutAddRequest.model_validate({**ENTRY, **change})

    def test_missing_field_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            CrashoutAddRequest.model_validate({'severity': 'heated'})


class TestNoArgumentRequests:
    @pytest.mark.parametrize('request_type', [CrashoutStatsRequest, CrashoutLastRequest])
    def test_takes_nothing(self, request_type: type[CrashoutStatsRequest]) -> None:
        assert request_type.model_validate({}).model_dump() == {}
        with pytest.raises(ValidationError):
            request_type.model_validate({'unknown': 1})


class TestSimilaritySearchRequest:
    def test_kind_defaults_to_none(self) -> None:
        request = SimilaritySearchRequest.model_validate({'query': 'q'})

        assert (request.query, request.kind) == ('q', None)

    def test_kind_is_taken(self) -> None:
        request = SimilaritySearchRequest.model_validate({'query': 'q', 'kind': 'crashout'})

        assert request.kind == 'crashout'

    @search_request_refused_cases()
    def test_invalid_search_is_refused(self, given: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            SimilaritySearchRequest.model_validate(given)
