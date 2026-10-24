"""The review start rules: target, weights, personas, models, the override and the reopened keys."""

from dataclasses import replace
from types import NoneType
from typing import TYPE_CHECKING, get_args

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.git import UnsafeRevisionError
from mightymodels_core.primitives import RunId, create_routing_table
from mightymodels_core.reviews import (
    BaseRequiredError,
    OverridePolicy,
    OverrideSpentError,
    PersonaChoiceError,
    ReviewOptions,
    SlugRequiredError,
    StartPolicy,
    WeightRangeError,
    WeightsMissingError,
    WeightSumError,
    reopened_keys,
)
from mightymodels_core.reviews.reports import MergeVaderBasis, PersonaSpec, UncleBobBasis
from mightymodels_core.vocabulary.reviews import Depth, Emphasis

from tests.core.reviews.review_builders import (
    HEAD,
    SERVICE_MOMENT,
    SLUG,
    create_finding,
    create_run,
)
from tests.core.reviews.service_builders import Case, create_request

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.reviews import StartRequest

BOTH = ['merge-vader', 'uncle-bob']
MV_HEAVY = {'merge-vader': 0.7, 'uncle-bob': 0.3}
MV_AT_LIMIT = {'merge-vader': 0.75, 'uncle-bob': 0.25}
MV_BELOW_LIMIT = {'merge-vader': 0.8, 'uncle-bob': 0.2}


type StartCase = Case[StartRequest, type[object]]


def custom(weights: dict[str, float] | None) -> StartRequest:
    return create_request(emphasis='custom', weights=weights)


def refusal_cases(cases: list[StartCase]) -> pytest.MarkDecorator:
    return pytest.mark.parametrize('case', [case.param for case in cases])


def target_cases() -> pytest.MarkDecorator:
    return refusal_cases([
        Case(
            name='branch-no-base', given=create_request(scope='branch'), expected=BaseRequiredError
        ),
        Case(
            name='ticket-no-base',
            given=create_request(scope='ticket', slug=SLUG),
            expected=BaseRequiredError,
        ),
        Case(
            name='ticket-no-slug',
            given=create_request(scope='ticket', base='main'),
            expected=SlugRequiredError,
        ),
        Case(
            name='base-is-an-option',
            given=create_request(scope='branch', base='--output=x'),
            expected=UnsafeRevisionError,
        ),
        Case(name='codebase-no-base', given=create_request(), expected=NoneType),
        Case(
            name='branch-with-base',
            given=create_request(scope='branch', base='main'),
            expected=NoneType,
        ),
    ])


def weights_cases() -> pytest.MarkDecorator:
    return refusal_cases([
        Case(name='missing', given=custom(None), expected=WeightsMissingError),
        Case(name='one-persona', given=custom({'merge-vader': 1.0}), expected=WeightRangeError),
        Case(
            name='unknown-persona',
            given=custom({'merge-vader': 0.5, 'other': 0.5}),
            expected=WeightRangeError,
        ),
        Case(
            name='out-of-range',
            given=custom({'merge-vader': 1.5, 'uncle-bob': -0.5}),
            expected=WeightRangeError,
        ),
        Case(
            name='sum-off-one',
            given=custom({'merge-vader': 0.8, 'uncle-bob': 0.8}),
            expected=WeightSumError,
        ),
        Case(
            name='sum-in-tolerance',
            given=custom({'merge-vader': 0.5005, 'uncle-bob': 0.5}),
            expected=NoneType,
        ),
        Case(
            name='preset-ignores-weights',
            given=create_request(weights={'merge-vader': 3.0}),
            expected=NoneType,
        ),
    ])


def persona_choice_cases() -> pytest.MarkDecorator:
    return refusal_cases([
        Case(name='quick-tie', given=create_request(depth='quick'), expected=PersonaChoiceError),
        Case(
            name='quick-tie-chosen',
            given=create_request(depth='quick', persona='uncle-bob'),
            expected=NoneType,
        ),
        Case(
            name='quick-heavier',
            given=create_request(depth='quick', emphasis='maintainability'),
            expected=NoneType,
        ),
        Case(name='deep-tie', given=create_request(), expected=NoneType),
    ])


def persona_cases() -> pytest.MarkDecorator:
    def run(depth: Depth, weights: dict[str, float]) -> StartRequest:
        return create_request(depth=depth, emphasis='custom', weights=weights)

    cases: list[Case[StartRequest, list[str]]] = [
        Case(name='deep-runs-both', given=run('deep', MV_BELOW_LIMIT), expected=BOTH),
        Case(name='standard-at-threshold', given=run('standard', MV_AT_LIMIT), expected=BOTH),
        Case(
            name='standard-below-threshold',
            given=run('standard', MV_BELOW_LIMIT),
            expected=['merge-vader'],
        ),
        Case(
            name='quick-runs-the-heavier',
            given=create_request(depth='quick', emphasis='maintainability'),
            expected=['uncle-bob'],
        ),
        Case(
            name='quick-runs-the-chosen',
            given=create_request(depth='quick', persona='merge-vader', emphasis='maintainability'),
            expected=['merge-vader'],
        ),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestStartPolicy:
    routing = create_routing_table()
    depths = st.sampled_from(get_args(Depth.__value__))
    preset_emphases = st.sampled_from([
        emphasis for emphasis in get_args(Emphasis.__value__) if emphasis != 'custom'
    ])

    def policy_of(self, request: StartRequest) -> StartPolicy:
        return StartPolicy(request=request, routing=self.routing)

    @target_cases()
    def test_target_rule(self, case: StartCase) -> None:
        assert type(self.policy_of(case.given).get_start_problem()) is case.expected

    @weights_cases()
    def test_weights_rule(self, case: StartCase) -> None:
        assert type(self.policy_of(case.given).get_start_problem()) is case.expected

    @persona_choice_cases()
    def test_persona_choice_rule(self, case: StartCase) -> None:
        assert type(self.policy_of(case.given).get_start_problem()) is case.expected

    @persona_cases()
    def test_personas_run_at_each_depth(self, case: Case[StartRequest, Sequence[str]]) -> None:
        assert self.policy_of(case.given).personas == case.expected

    @given(depth=depths)
    @example(depth='quick')
    @example(depth='standard')
    @example(depth='deep')
    def test_each_persona_reviews_on_the_depth_model(self, depth: Depth) -> None:
        expected = {
            'quick': dict.fromkeys(['uncle-bob'], 'sonnet'),
            'standard': dict.fromkeys(BOTH, 'opus'),
            'deep': dict.fromkeys(BOTH, 'opus'),
        }
        policy = self.policy_of(create_request(depth=depth, persona='uncle-bob'))
        assert policy.reviewer_models == expected[depth]

    @given(emphasis=preset_emphases)
    @example(emphasis='release-readiness')
    @example(emphasis='maintainability')
    @example(emphasis='balanced')
    def test_preset_weights(self, emphasis: Emphasis) -> None:
        expected = {
            'release-readiness': MV_HEAVY,
            'maintainability': {'merge-vader': 0.3, 'uncle-bob': 0.7},
            'balanced': {'merge-vader': 0.5, 'uncle-bob': 0.5},
        }
        assert self.policy_of(create_request(emphasis=emphasis)).weights == expected[emphasis]

    def test_target_is_refused_before_weights(self) -> None:
        request = create_request(scope='branch', emphasis='custom')
        assert type(self.policy_of(request).get_start_problem()) is BaseRequiredError

    def test_record_carries_head_moment_and_run_id(self) -> None:
        record = self.policy_of(create_request()).record_for(HEAD, SERVICE_MOMENT)
        assert (record.run_id, record.head, record.created_at) == (
            RunId('20260506-070809'),
            HEAD,
            SERVICE_MOMENT,
        )


class TestOverridePolicy:
    routing = create_routing_table()

    def policy_of(self, **changes: object) -> OverridePolicy:
        return OverridePolicy(run=replace(create_run(), **changes), routing=self.routing)

    def test_fresh_run_may_override(self) -> None:
        assert self.policy_of().get_override_problem() is None

    def test_run_on_the_override_model_is_spent(self) -> None:
        policy = self.policy_of(models={'merge-vader': 'fable', 'uncle-bob': None})
        assert isinstance(policy.get_override_problem(), OverrideSpentError)

    def test_override_moves_the_heavier_persona(self) -> None:
        policy = self.policy_of(weights={'merge-vader': 0.3, 'uncle-bob': 0.7})
        assert policy.overridden_models == {'merge-vader': 'opus', 'uncle-bob': 'fable'}

    def test_tied_weights_override_the_first_persona(self) -> None:
        assert self.policy_of().heavier_persona == 'merge-vader'


class TestReviewOptions:
    @pytest.fixture
    def options(self) -> ReviewOptions:
        weights: dict[Emphasis, float] = {
            'release-readiness': 0.6,
            'maintainability': 0.4,
            'balanced': 0.5,
        }
        return ReviewOptions(
            specs={
                'merge-vader': PersonaSpec(prefix='MX', parser=MergeVaderBasis(), weights=weights),
                'uncle-bob': PersonaSpec(prefix='UB', parser=UncleBobBasis(), weights=weights),
            }
        )

    def test_source_personas_follow_the_specs(self, options: ReviewOptions) -> None:
        assert options.source_personas['MX'] == 'merge-vader'

    def test_finding_sources_follow_the_specs(self, options: ReviewOptions) -> None:
        assert options.findings.source_id.match('MX-1')

    def test_presets_follow_the_specs(self, options: ReviewOptions) -> None:
        assert options.presets['release-readiness'] == {'merge-vader': 0.6, 'uncle-bob': 0.6}


class TestReopenedKeys:
    held = (create_finding('F1'), create_finding('F2'))
    edited = create_finding('F1', title='changed')

    def test_decided_finding_the_batch_changed_is_reopened(self) -> None:
        assert reopened_keys(self.held, [self.edited], {'F1'}) == ['F1']

    def test_undecided_finding_stays_as_it_was(self) -> None:
        assert reopened_keys(self.held, [self.edited], {'F2'}) == []

    def test_decided_finding_the_batch_left_equal_is_not_reopened(self) -> None:
        assert reopened_keys(self.held, [self.held[0]], {'F1'}) == []
