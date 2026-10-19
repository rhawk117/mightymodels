"""The entry rules, the batch rules, the redacted records and the investigation names."""

from types import NoneType
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.investigations import (
    BatchPolicy,
    CiteRequiredError,
    EmptyTextError,
    EntryPolicy,
    EntryStamp,
    InvestigationOptions,
    NamePolicy,
    RoundRegressionError,
    SourceNotAllowedError,
    UnknownSupersededError,
)
from mightymodels_core.primitives import RedactedTextTooLongError

from .conftest import HEAD, MOMENT, Case, create_incoming

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.investigations import IncomingEntry

type EntryCase = Case[IncomingEntry, type[object]]


def entry_rule_cases() -> pytest.MarkDecorator:
    cases = [
        Case(
            name='known-needs-a-cite',
            given=create_incoming('known', cite=None),
            expected=CiteRequiredError,
        ),
        Case(
            name='resource-needs-a-cite',
            given=create_incoming('resource', cite=None),
            expected=CiteRequiredError,
        ),
        Case(
            name='open-needs-no-cite',
            given=create_incoming('open', cite=None, source='primary'),
            expected=NoneType,
        ),
        Case(
            name='decision-only-from-the-user',
            given=create_incoming('decision', source='primary', cite=None),
            expected=SourceNotAllowedError,
        ),
        Case(
            name='decision-from-the-user',
            given=create_incoming('decision', source='user', cite=None),
            expected=NoneType,
        ),
        Case(
            name='next-not-from-primary',
            given=create_incoming('next', source='primary', cite=None),
            expected=SourceNotAllowedError,
        ),
        Case(
            name='next-from-a-scout',
            given=create_incoming('next', source='web-scout', cite=None),
            expected=NoneType,
        ),
        Case(
            name='known-from-primary',
            given=create_incoming('known', source='primary'),
            expected=NoneType,
        ),
        Case(
            name='blank-text',
            given=create_incoming('known', text='  \n', cite=None),
            expected=EmptyTextError,
        ),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


def unknown_superseded_cases() -> pytest.MarkDecorator:
    cases = [
        Case(name='held-seq', given=(2,), expected=NoneType),
        Case(name='unheld-seq', given=(3,), expected=UnknownSupersededError),
        Case(name='one-unheld-among-held', given=(1, 7), expected=UnknownSupersededError),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestEntryPolicy:
    def find_problem(self, entry: IncomingEntry, supersedable: Sequence[int] = (1, 2)) -> object:
        return EntryPolicy(index=0, entry=entry, supersedable=supersedable).get_entry_problem()

    @entry_rule_cases()
    def test_entry_rule(self, case: EntryCase) -> None:
        assert type(self.find_problem(case.given)) is case.expected

    @unknown_superseded_cases()
    def test_unknown_superseded_entries(self, case: Case[tuple[int, ...], type[object]]) -> None:
        entry = create_incoming(supersedes=case.given)
        assert type(self.find_problem(entry)) is case.expected

    def test_unknown_superseded_names_the_unheld_entries_in_order(self) -> None:
        problem = self.find_problem(create_incoming(supersedes=(9, 1, 7)))
        assert isinstance(problem, UnknownSupersededError)
        assert problem.unknown == (7, 9)

    def test_empty_text_is_reported_before_a_missing_cite(self) -> None:
        problem = self.find_problem(create_incoming(text='', cite=None))
        assert isinstance(problem, EmptyTextError)

    def test_missing_cite_is_reported_before_the_source(self) -> None:
        problem = self.find_problem(create_incoming('known', cite=None, supersedes=(8,)))
        assert isinstance(problem, CiteRequiredError)


class TestBatchPolicy:
    stamp = EntryStamp(round=2, at=MOMENT, head=HEAD)

    def create_policy(
        self, entries: Sequence[IncomingEntry], *, latest_round: int = 2
    ) -> BatchPolicy:
        return BatchPolicy(
            latest_round=latest_round, supersedable={1}, stamp=self.stamp, entries=entries
        )

    def test_a_round_before_the_latest_is_refused(self) -> None:
        problem = self.create_policy([create_incoming()], latest_round=3).get_batch_problem()
        assert isinstance(problem, RoundRegressionError)
        assert (problem.given, problem.latest) == (2, 3)

    def test_the_latest_round_again_is_accepted(self) -> None:
        assert self.create_policy([create_incoming()]).get_batch_problem() is None

    def test_a_regressed_round_is_reported_before_a_bad_entry(self) -> None:
        bad = create_incoming(text='')
        problem = self.create_policy([bad], latest_round=3).get_batch_problem()
        assert isinstance(problem, RoundRegressionError)

    def test_the_first_bad_entry_refuses_the_batch(self) -> None:
        entries = [create_incoming(), create_incoming(cite=None), create_incoming(text='')]
        problem = self.create_policy(entries).get_batch_problem()
        assert isinstance(problem, CiteRequiredError)
        assert problem.index == 1

    def test_records_are_numbered_from_the_first_seq_and_stamped(self) -> None:
        redacted = self.create_policy([create_incoming(), create_incoming()]).redacted_records(5)
        assert [item.record.seq for item in redacted] == [5, 6]
        assert {(item.record.round, item.record.at, item.record.head) for item in redacted} == {
            (2, MOMENT, HEAD)
        }

    def test_secrets_in_text_and_cite_are_redacted_and_counted(self) -> None:
        secret = 'ghp_' + 'a' * 36
        entry = create_incoming(text=f'token {secret}', cite=f'https://x/{secret}#top')
        [redacted] = self.create_policy([entry]).redacted_records(1)
        assert secret not in redacted.record.text
        assert redacted.record.cite is not None
        assert secret not in redacted.record.cite
        assert redacted.hits == 2

    def test_a_missing_cite_stays_missing(self) -> None:
        [redacted] = self.create_policy([create_incoming('open', cite=None)]).redacted_records(1)
        assert redacted.record.cite is None
        assert redacted.hits == 0

    def test_text_past_the_prose_limit_is_refused(self) -> None:
        policy = BatchPolicy(
            latest_round=0,
            supersedable=(),
            stamp=self.stamp,
            entries=[create_incoming(text='x' * 11)],
            options=InvestigationOptions(prose_limit=10),
        )
        with pytest.raises(RedactedTextTooLongError):
            policy.redacted_records(1)


def target_name_cases() -> pytest.MarkDecorator:
    cases = [
        Case(
            name='lowercased-and-dashed',
            given='Fix the Retry Policy!',
            expected='fix-the-retry-policy',
        ),
        Case(name='runs-collapse', given='a  /  b__c', expected='a-b-c'),
        Case(name='nothing-usable', given='!!! ???', expected='investigation'),
        Case(name='empty', given='', expected='investigation'),
        Case(
            name='cut-at-a-word-boundary',
            given='alpha ' * 4 + 'beta gamma deltas epsilon',
            expected='alpha-alpha-alpha-alpha-beta-gamma',
        ),
        Case(name='one-long-word-is-cut', given='w' * 60, expected='w' * 40),
        Case(name='exactly-the-limit', given='w' * 40, expected='w' * 40),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestNamePolicy:
    def create_policy(self, target: str) -> NamePolicy:
        return NamePolicy(target=target, day=MOMENT)

    @target_name_cases()
    def test_target_name(self, case: Case[str, str]) -> None:
        assert self.create_policy(case.given).target_name == case.expected

    def test_the_stem_is_the_day_and_the_target(self) -> None:
        assert self.create_policy('Retry policy').stem == '20260506-retry-policy'

    def test_names_repeat_with_a_counter(self) -> None:
        names = self.create_policy('Retry policy').names()
        assert [next(names) for _ in range(3)] == [
            '20260506-retry-policy',
            '20260506-retry-policy-2',
            '20260506-retry-policy-3',
        ]
