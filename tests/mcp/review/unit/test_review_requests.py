from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest
from mightymodels_mcp.review.schemas import (
    Disposition,
    ReviewAddRequest,
    ReviewDisposeRequest,
    ReviewGateRequest,
    ReviewListRequest,
    ReviewOverrideRequest,
    ReviewReportRequest,
    ReviewResolveRequest,
    ReviewStartRequest,
)
from pydantic import ValidationError

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_mcp.server.requests import RequestModel

RUN_ID = '20260101-000001'
PERSONAS = ('merge-vader', 'uncle-bob')


RUN_REQUESTS: dict[str, type[RequestModel]] = {
    'override': ReviewOverrideRequest,
    'gate': ReviewGateRequest,
    'add': ReviewAddRequest,
    'report': ReviewReportRequest,
    'dispose': ReviewDisposeRequest,
    'resolve': ReviewResolveRequest,
}
INVALID_RUN_IDS: dict[str, str] = {
    'empty': '',
    'dashed-date': '2026-01-01',
    'short': '20260101-00000',
    'trailing-newline': f'{RUN_ID}\n',
    'prefixed': f'x{RUN_ID}',
}


def malformed_run_requests() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param(request_type, raw, id=f'{request_name}-{raw_name}')
        for request_name, request_type in RUN_REQUESTS.items()
        for raw_name, raw in INVALID_RUN_IDS.items()
    ]
    return pytest.mark.parametrize(('request_type', 'raw'), cases)


class TestReviewStartRequest:
    def test_every_field_defaults_to_none(self) -> None:
        request = ReviewStartRequest.model_validate({})

        assert request.model_dump() == dict.fromkeys((
            'scope',
            'depth',
            'emphasis',
            'slug',
            'base',
            'weights',
            'persona',
        ))

    def test_every_field_is_taken(self) -> None:
        request = ReviewStartRequest.model_validate({
            'scope': 'branch',
            'depth': 'quick',
            'emphasis': 'custom',
            'slug': 'probe-ticket',
            'base': 'main',
            'weights': {'merge-vader': 0.25, 'uncle-bob': 0.75},
            'persona': 'uncle-bob',
        })

        assert (request.scope, request.depth, request.emphasis) == ('branch', 'quick', 'custom')
        assert (request.slug, request.base, request.persona) == (
            'probe-ticket',
            'main',
            'uncle-bob',
        )
        assert request.weights == {'merge-vader': 0.25, 'uncle-bob': 0.75}

    @pytest.mark.parametrize(
        'given',
        [
            pytest.param({'base': '--output=x'}, id='dash-base'),
            pytest.param({'slug': 'Not A Slug'}, id='slug'),
            pytest.param({'scope': 'galaxy'}, id='scope'),
            pytest.param({'depth': 'abyssal'}, id='depth'),
            pytest.param({'emphasis': 'vibes'}, id='emphasis'),
            pytest.param({'persona': 'wizard'}, id='persona'),
            pytest.param({'weights': {'wizard': 1.0}}, id='weights-persona'),
            pytest.param({'unknown': 'field'}, id='extra-field'),
        ],
    )
    def test_invalid_field_is_refused(self, given: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            ReviewStartRequest.model_validate(given)


class TestRunRequests:
    @pytest.mark.parametrize('request_type', [ReviewOverrideRequest, ReviewGateRequest])
    def test_run_id_is_taken(self, request_type: type[ReviewOverrideRequest]) -> None:
        assert request_type.model_validate({'run_id': RUN_ID}).run_id == RUN_ID

    @malformed_run_requests()
    def test_malformed_run_id_is_refused(self, request_type: type[RequestModel], raw: str) -> None:
        given = MappingProxyType({
            'run_id': raw,
            'persona': 'merge-vader',
            'finding': 'F1',
            'result': 'fixed',
        })
        fields = {key: value for key, value in given.items() if key in request_type.model_fields}

        with pytest.raises(ValidationError):
            request_type.model_validate(fields)

    def test_run_id_publishes_no_pattern(self) -> None:
        schema = ReviewGateRequest.model_json_schema()

        assert 'pattern' not in schema['properties']['run_id']

    def test_unknown_argument_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ReviewGateRequest.model_validate({'run_id': RUN_ID, 'unknown': 'field'})


class TestReviewAddRequest:
    @pytest.mark.parametrize('persona', PERSONAS)
    def test_persona_is_taken(self, persona: str) -> None:
        request = ReviewAddRequest.model_validate({'run_id': RUN_ID, 'persona': persona})

        assert request.persona == persona

    def test_persona_is_required(self) -> None:
        with pytest.raises(ValidationError):
            ReviewAddRequest.model_validate({'run_id': RUN_ID})

    def test_unknown_persona_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ReviewAddRequest.model_validate({'run_id': RUN_ID, 'persona': 'wizard'})


class TestReviewReportRequest:
    def test_shape_defaults_to_full(self) -> None:
        assert ReviewReportRequest.model_validate({'run_id': RUN_ID}).shape == 'full'

    def test_comment_shape_is_taken(self) -> None:
        request = ReviewReportRequest.model_validate({'run_id': RUN_ID, 'shape': 'comment'})

        assert request.shape == 'comment'

    def test_unknown_shape_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ReviewReportRequest.model_validate({'run_id': RUN_ID, 'shape': 'poem'})


class TestReviewListRequest:
    def test_list_takes_nothing(self) -> None:
        assert ReviewListRequest.model_validate({}) == ReviewListRequest()

    def test_any_argument_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ReviewListRequest.model_validate({'run_id': RUN_ID})


def dispose_invalid_decision_cases() -> pytest.MarkDecorator:
    decisions: list[ParameterSet] = [
        pytest.param({'F1': {'decision': 'shrug'}}, id='unknown-decision'),
        pytest.param({'F1': {'decision': 'fix', 'note': 'x'}}, id='unknown-key'),
        pytest.param({'F1': {'reason': 'why'}}, id='missing-decision'),
        pytest.param({'F1': {'decision': 'dismiss', 'reason': 'x' * 4001}}, id='long-reason'),
    ]
    return pytest.mark.parametrize('decisions', decisions)


def resolve_invalid_field_cases() -> pytest.MarkDecorator:
    fields: list[ParameterSet] = [
        pytest.param({'result': 'fixed'}, id='missing-finding'),
        pytest.param({'finding': 'F1'}, id='missing-result'),
        pytest.param({'finding': 'F1', 'result': 'done'}, id='unknown-result'),
    ]
    return pytest.mark.parametrize('given', fields)


class TestReviewDisposeRequest:
    def test_decisions_and_by_default_to_none_and_blank(self) -> None:
        request = ReviewDisposeRequest.model_validate({'run_id': RUN_ID})

        assert (request.decisions, request.by) == (None, '')

    def test_decisions_are_taken_with_a_blank_default_reason(self) -> None:
        given = {'F1': {'decision': 'fix'}, 'F2': {'decision': 'dismiss', 'reason': 'noise'}}

        request = ReviewDisposeRequest.model_validate({
            'run_id': RUN_ID,
            'decisions': given,
            'by': 'owner',
        })

        assert request.decisions == {
            'F1': Disposition(decision='fix'),
            'F2': Disposition(decision='dismiss', reason='noise'),
        }

    @pytest.mark.parametrize('by', [None, '', '  '])
    def test_decisions_without_an_approver_are_refused(self, by: str | None) -> None:
        given: dict[str, Any] = {'run_id': RUN_ID, 'decisions': {'F1': {'decision': 'fix'}}}
        if by is not None:
            given['by'] = by

        with pytest.raises(ValidationError):
            ReviewDisposeRequest.model_validate(given)

    @dispose_invalid_decision_cases()
    def test_invalid_decision_is_refused(self, decisions: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            ReviewDisposeRequest.model_validate({'run_id': RUN_ID, 'decisions': decisions})


class TestReviewResolveRequest:
    def test_commit_and_reason_default_to_none(self) -> None:
        given = {'run_id': RUN_ID, 'finding': 'F1', 'result': 'fixed'}

        request = ReviewResolveRequest.model_validate(given)

        assert (request.finding, request.result) == ('F1', 'fixed')
        assert (request.commit, request.reason) == (None, None)

    @resolve_invalid_field_cases()
    def test_invalid_field_is_refused(self, given: dict[str, str]) -> None:
        with pytest.raises(ValidationError):
            ReviewResolveRequest.model_validate({'run_id': RUN_ID, **given})
