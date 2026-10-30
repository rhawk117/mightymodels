"""The value checks of the review signals request models."""

import pytest
from mightymodels_mcp.review_signals.schemas import ChangeCouplingRequest
from pydantic import ValidationError


class TestRefusedValues:
    @pytest.mark.parametrize(
        'fields',
        [
            pytest.param({'since': '--output=/tmp/x'}, id='option-shaped-since'),
            pytest.param({'since': '$(id)'}, id='shell-shaped-since'),
            pytest.param({'baseline_ref': '--output=/tmp/x'}, id='option-shaped-baseline-ref'),
            pytest.param({'baseline_ref': 'main branch'}, id='baseline-ref-holding-a-space'),
        ],
    )
    def test_a_value_that_is_not_plain_is_refused(self, fields: dict[str, str]) -> None:
        with pytest.raises(ValidationError, match='should match pattern'):
            ChangeCouplingRequest.model_validate(fields)

    @pytest.mark.parametrize(
        'fields',
        [
            pytest.param({'max_commits': 0}, id='max-commits'),
            pytest.param({'limit': 0}, id='limit'),
            pytest.param({'min_shared': 0}, id='min-shared'),
            pytest.param({'max_changeset': -1}, id='max-changeset'),
        ],
    )
    def test_a_count_below_one_is_refused(self, fields: dict[str, int]) -> None:
        with pytest.raises(ValidationError, match='greater than or equal to 1'):
            ChangeCouplingRequest.model_validate(fields)


class TestAcceptedValues:
    @pytest.mark.parametrize(
        'fields',
        [
            pytest.param({'since': '6 months ago'}, id='since-holding-a-space'),
            pytest.param({'since': '2026-01-01'}, id='since-date'),
            pytest.param({'baseline_ref': 'release/1.2'}, id='baseline-ref-with-a-slash'),
            pytest.param({'target': '--output=report'}, id='option-shaped-target'),
        ],
    )
    def test_a_plain_value_is_accepted(self, fields: dict[str, str]) -> None:
        dumped = ChangeCouplingRequest.model_validate(fields).model_dump()

        assert {name: dumped[name] for name in fields} == fields

    def test_the_defaults_match_the_command_line(self) -> None:
        options = ChangeCouplingRequest()

        assert (options.max_commits, options.limit, options.min_shared, options.max_changeset) == (
            500,
            25,
            3,
            50,
        )
