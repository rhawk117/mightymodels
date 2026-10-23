"""The review decision service over fakes: dispose, resolve and the latest review."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.git import UnsafeRevisionError
from mightymodels_core.reviews import (
    CommitRequiredError,
    IncomingDisposition,
    NotChosenError,
    ReasonRequiredError,
    ResolveRequest,
    ResultReasonError,
    RunNotFoundError,
    UnknownFindingError,
)

from tests.core.reviews.conftest import (
    FIRST_RUN,
    OTHER_SLUG,
    SLUG,
    UNSTARTED_RUN,
    Case,
    create_decided,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.core.reviews.conftest import DecisionHarness

type Refusal = type[Exception]
FIX_MV_1 = IncomingDisposition(decision='fix')
FIXED_MV_1 = ResolveRequest(finding_key='MV-1', result='fixed', commit='abc1234')


def reason_required_cases() -> pytest.MarkDecorator:
    accept_risk = IncomingDisposition(decision='accept-risk', reason='  ')
    dismiss = IncomingDisposition(decision='dismiss')
    return pytest.mark.parametrize(
        'entry', [pytest.param(accept_risk, id='accept-risk'), pytest.param(dismiss, id='dismiss')]
    )


def resolve_refusal_cases() -> pytest.MarkDecorator:
    cases: list[Case[ResolveRequest, Refusal]] = [
        Case(
            name='unknown-finding',
            given=ResolveRequest(finding_key='MV-9', result='fixed', commit='abc1234'),
            expected=UnknownFindingError,
        ),
        Case(
            name='not-chosen-for-fixing',
            given=ResolveRequest(finding_key='MV-2', result='fixed', commit='abc1234'),
            expected=NotChosenError,
        ),
        Case(
            name='not-decided',
            given=ResolveRequest(finding_key='MV-3', result='fixed', commit='abc1234'),
            expected=NotChosenError,
        ),
        Case(
            name='unsafe-revision',
            given=ResolveRequest(finding_key='MV-1', result='fixed', commit='--force'),
            expected=UnsafeRevisionError,
        ),
        Case(
            name='commit-required',
            given=ResolveRequest(finding_key='MV-1', result='fixed'),
            expected=CommitRequiredError,
        ),
        Case(
            name='failed-without-reason',
            given=ResolveRequest(finding_key='MV-1', result='failed'),
            expected=ResultReasonError,
        ),
        Case(
            name='blocked-with-blank-reason',
            given=ResolveRequest(finding_key='MV-1', result='blocked', reason=' '),
            expected=ResultReasonError,
        ),
    ]
    params: list[ParameterSet] = [case.param for case in cases]
    return pytest.mark.parametrize('case', params)


class TestDispose:
    def test_records_decisions_and_lists_the_undecided(
        self, decision_harness: DecisionHarness
    ) -> None:
        disposed = decision_harness.service.dispose(FIRST_RUN, {'MV-2': FIX_MV_1}, by='owner')

        assert disposed.recorded == 1
        assert disposed.undecided == ('MV-1', 'MV-3')
        assert [
            item.finding_key for item in decision_harness.decisions.dispositions(FIRST_RUN)
        ] == ['MV-2']

    def test_unknown_run_is_refused(self, decision_harness: DecisionHarness) -> None:
        with pytest.raises(RunNotFoundError):
            decision_harness.service.dispose(UNSTARTED_RUN, {'MV-1': FIX_MV_1}, by='owner')

    def test_unknown_finding_is_refused_before_any_write(
        self, decision_harness: DecisionHarness
    ) -> None:
        batch = {'MV-1': FIX_MV_1, 'MV-9': FIX_MV_1}

        with pytest.raises(UnknownFindingError):
            decision_harness.service.dispose(FIRST_RUN, batch, by='owner')

        assert decision_harness.decisions.dispositions(FIRST_RUN) == []

    @reason_required_cases()
    def test_decision_without_reason_is_refused_before_any_write(
        self, decision_harness: DecisionHarness, entry: IncomingDisposition
    ) -> None:
        with pytest.raises(ReasonRequiredError):
            decision_harness.service.dispose(
                FIRST_RUN, {'MV-1': FIX_MV_1, 'MV-2': entry}, by='owner'
            )

        assert decision_harness.decisions.dispositions(FIRST_RUN) == []


class TestResolve:
    def test_fixed_outcome_is_recorded(self, chosen_harness: DecisionHarness) -> None:
        resolved = chosen_harness.service.resolve(FIRST_RUN, FIXED_MV_1)

        assert chosen_harness.decisions.outcomes(FIRST_RUN) == [resolved]
        assert (resolved.result, resolved.commit) == ('fixed', 'abc1234')

    def test_failed_outcome_keeps_its_reason(self, chosen_harness: DecisionHarness) -> None:
        request = ResolveRequest(finding_key='MV-1', result='failed', reason='tests broke')

        resolved = chosen_harness.service.resolve(FIRST_RUN, request)

        assert (resolved.result, resolved.commit, resolved.reason) == ('failed', '', 'tests broke')

    def test_unknown_run_is_refused(self, chosen_harness: DecisionHarness) -> None:
        with pytest.raises(RunNotFoundError):
            chosen_harness.service.resolve(UNSTARTED_RUN, FIXED_MV_1)

    @resolve_refusal_cases()
    def test_refusal_writes_nothing(
        self, chosen_harness: DecisionHarness, case: Case[ResolveRequest, Refusal]
    ) -> None:
        with pytest.raises(case.expected):
            chosen_harness.service.resolve(FIRST_RUN, case.given)

        assert chosen_harness.decisions.outcomes(FIRST_RUN) == []


class TestLatestReview:
    def test_ticket_without_a_run_has_none(self, decision_harness: DecisionHarness) -> None:
        assert decision_harness.service.latest_review(OTHER_SLUG) is None

    def test_state_of_decided_undecided_fixed_and_open(
        self, chosen_harness: DecisionHarness
    ) -> None:
        chosen_harness.decisions.record_dispositions(
            FIRST_RUN, [create_decided('MV-3', decision='fix')]
        )
        chosen_harness.service.resolve(FIRST_RUN, FIXED_MV_1)

        latest = chosen_harness.service.latest_review(SLUG)

        assert latest is not None
        assert [item.finding_key for item in latest.decided] == ['MV-1', 'MV-2', 'MV-3']
        assert latest.undecided == ()
        assert latest.is_fixed('MV-1')
        assert not latest.is_fixed('MV-3')
        assert latest.open_remediation == ('MV-3',)

    def test_undecided_findings_keep_finding_order(self, chosen_harness: DecisionHarness) -> None:
        latest = chosen_harness.service.latest_review(SLUG)

        assert latest is not None
        assert latest.undecided == ('MV-3',)
        assert latest.open_remediation == ('MV-1',)
