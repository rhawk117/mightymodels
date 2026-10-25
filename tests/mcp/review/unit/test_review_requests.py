from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest
from mightymodels_mcp.review.schemas import (
    ReviewAddRequest,
    ReviewGateRequest,
    ReviewListRequest,
    ReviewOverrideRequest,
    ReviewReportRequest,
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
        given = MappingProxyType({'run_id': raw, 'persona': 'merge-vader'})
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
