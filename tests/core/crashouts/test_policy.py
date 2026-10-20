"""The crashout rules: what refuses an entry, and the record built from one that passes."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.crashouts import (
    BlankCrashoutFieldError,
    CrashoutOptions,
    CrashoutPolicy,
    NoFailuresError,
    normalized_rant,
)
from mightymodels_core.primitives import RedactedTextTooLongError

from .conftest import MOMENT, create_entry

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.crashouts import CrashoutEntry, CrashoutRecord


SHORT_ENTRY = create_entry(
    rant='r', failures=('f',), root_cause='c', corrective_action='a', branch='b'
)


def blank_field_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param(create_entry(rant='  \n '), 'rant', id='rant'),
        pytest.param(create_entry(failures=('ok', ' \t')), 'failures', id='failure'),
        pytest.param(create_entry(root_cause='  '), 'root_cause', id='root-cause'),
        pytest.param(create_entry(corrective_action=''), 'corrective_action', id='action'),
    ]
    return pytest.mark.parametrize(('entry', 'field'), cases)


def too_long_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param(replace(SHORT_ENTRY, branch='b' * 6), 'branch', id='branch'),
        pytest.param(replace(SHORT_ENTRY, rant='r' * 6), 'rant', id='rant'),
        pytest.param(replace(SHORT_ENTRY, failures=('f' * 6,)), 'failures', id='failure'),
        pytest.param(replace(SHORT_ENTRY, root_cause='c' * 6), 'root_cause', id='root-cause'),
        pytest.param(
            replace(SHORT_ENTRY, corrective_action='a' * 6), 'corrective_action', id='action'
        ),
    ]
    return pytest.mark.parametrize(('entry', 'field'), cases)


@pytest.mark.parametrize(
    ('rant', 'expected'),
    [
        pytest.param('a  \r\nb\r\n', 'a\nb', id='crlf'),
        pytest.param('a\rb', 'a\nb', id='cr'),
        pytest.param('\n\n  a\n   b  \n\n', '  a\n   b', id='indent-kept'),
    ],
)
def test_the_rant_loses_its_line_endings_and_keeps_its_words(rant: str, expected: str) -> None:
    assert normalized_rant(rant) == expected


class TestEntryProblem:
    options = CrashoutOptions(name_limit=5, prose_limit=5)

    def find_problem(self, entry: CrashoutEntry) -> object:
        return CrashoutPolicy(entry=entry, options=self.options).get_entry_problem()

    def test_a_complete_entry_has_no_problem(self) -> None:
        assert self.find_problem(SHORT_ENTRY) is None

    def test_an_entry_without_failures_is_refused(self) -> None:
        assert isinstance(self.find_problem(create_entry(failures=())), NoFailuresError)

    @blank_field_cases()
    def test_a_blank_text_is_refused_by_its_field(self, entry: CrashoutEntry, field: str) -> None:
        problem = self.find_problem(entry)
        assert isinstance(problem, BlankCrashoutFieldError)
        assert problem.field == field

    @too_long_cases()
    def test_text_redaction_leaves_too_long_is_refused(
        self, entry: CrashoutEntry, field: str
    ) -> None:
        policy = CrashoutPolicy(entry=entry, options=self.options)
        with pytest.raises(RedactedTextTooLongError) as raised:
            policy.crashout_record(MOMENT)
        assert raised.value.field == field

    def test_text_at_the_limit_is_kept(self) -> None:
        entry = replace(SHORT_ENTRY, rant='r' * 5, branch='b' * 5)
        record = CrashoutPolicy(entry=entry, options=self.options).crashout_record(MOMENT)
        assert (record.rant, record.branch) == ('r' * 5, 'b' * 5)


class TestCrashoutRecord:
    def build_record(self, entry: CrashoutEntry) -> CrashoutRecord:
        return CrashoutPolicy(entry=entry, options=CrashoutOptions()).crashout_record(MOMENT)

    def test_the_root_cause_and_the_action_are_stripped(self) -> None:
        entry = create_entry(root_cause='  why \n', corrective_action=' a  b ')
        record = self.build_record(entry)
        assert (record.root_cause, record.corrective_action) == ('why', 'a  b')

    def test_the_rant_is_normalized_in_the_record(self) -> None:
        record = self.build_record(create_entry(rant='a  \r\n  b\r\n'))
        assert record.rant == 'a\n  b'

    def test_a_secret_is_redacted_before_it_is_stored(self) -> None:
        secret = 'ghp_' + 'a' * 36
        record = self.build_record(replace(create_entry(), root_cause=f'leaked {secret}'))
        assert secret not in record.root_cause

    def test_the_record_carries_the_time_it_was_given(self) -> None:
        assert self.build_record(create_entry()).at == MOMENT

    def test_an_absent_branch_stays_absent(self) -> None:
        assert self.build_record(create_entry(branch=None)).branch is None
