"""The crashout rules: what refuses an entry, and the record built from one that passes."""

import string
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.crashouts import (
    BlankCrashoutFieldError,
    CrashoutOptions,
    CrashoutPolicy,
    NoFailuresError,
    normalized_rant,
)
from mightymodels_core.primitives import RedactedTextTooLongError

from tests.core.crashouts.crashout_builders import MOMENT, create_entry

if TYPE_CHECKING:
    from mightymodels_core.crashouts import CrashoutEntry, CrashoutRecord


SHORT_ENTRY = create_entry(
    rant='r', failures=('f',), root_cause='c', corrective_action='a', branch='b'
)


class TestNormalizedRant:
    rant_lines = st.lists(
        st.tuples(
            st.text(alphabet=string.ascii_lowercase + ' ').map(str.rstrip),
            st.text(alphabet=' \t'),
        )
    )
    line_endings = st.sampled_from(['\r\n', '\r', '\n'])

    @given(rant_lines=rant_lines, line_ending=line_endings)
    @example(rant_lines=[('a', '  '), ('b', ''), ('', '')], line_ending='\r\n')
    @example(rant_lines=[('a', ''), ('b', '')], line_ending='\r')
    @example(
        rant_lines=[('', ''), ('', ''), ('  a', ''), ('   b', '  '), ('', ''), ('', '')],
        line_ending='\n',
    )
    def test_the_rant_loses_its_line_endings_and_keeps_its_words(
        self, rant_lines: list[tuple[str, str]], line_ending: str
    ) -> None:
        rant = line_ending.join(line + trailing for line, trailing in rant_lines)
        words = '\n'.join(line for line, _ in rant_lines).strip('\n')
        assert normalized_rant(rant) == words


class TestEntryProblem:
    options = CrashoutOptions(name_limit=5, prose_limit=5)
    blank_fields = st.sampled_from(['rant', 'failures', 'root_cause', 'corrective_action'])
    blank_texts = st.text(alphabet=' \t\r\n\x0b\x0c\u00a0\u2003')
    too_long_fields = st.sampled_from([
        'branch',
        'rant',
        'failures',
        'root_cause',
        'corrective_action',
    ])
    # Over both limits, and with nothing for redaction or whitespace trimming to change.
    too_long_texts = st.text(alphabet=string.ascii_lowercase + string.digits, min_size=6)

    def find_problem(self, entry: CrashoutEntry) -> object:
        return CrashoutPolicy(entry=entry, options=self.options).get_entry_problem()

    def test_a_complete_entry_has_no_problem(self) -> None:
        assert self.find_problem(SHORT_ENTRY) is None

    def test_an_entry_without_failures_is_refused(self) -> None:
        assert isinstance(self.find_problem(create_entry(failures=())), NoFailuresError)

    def create_entry_with(
        self, field: str, text: str, *, earlier_failures: tuple[str, ...] = ()
    ) -> CrashoutEntry:
        if field == 'failures':
            return replace(SHORT_ENTRY, failures=(*earlier_failures, text))
        return replace(SHORT_ENTRY, **{field: text})

    @given(field=blank_fields, text=blank_texts)
    @example(field='rant', text='  \n ')
    @example(field='failures', text=' \t')
    @example(field='root_cause', text='  ')
    @example(field='corrective_action', text='')
    def test_a_blank_text_is_refused_by_its_field(self, field: str, text: str) -> None:
        entry = self.create_entry_with(field, text, earlier_failures=('ok',))
        problem = self.find_problem(entry)
        assert isinstance(problem, BlankCrashoutFieldError)
        assert problem.field == field

    @given(field=too_long_fields, text=too_long_texts)
    @example(field='branch', text='b' * 6)
    @example(field='rant', text='r' * 6)
    @example(field='failures', text='f' * 6)
    @example(field='root_cause', text='c' * 6)
    @example(field='corrective_action', text='a' * 6)
    def test_text_redaction_leaves_too_long_is_refused(self, field: str, text: str) -> None:
        entry = self.create_entry_with(field, text)
        policy = CrashoutPolicy(entry=entry, options=self.options)
        with pytest.raises(RedactedTextTooLongError) as raised:
            policy.crashout_record(MOMENT)
        assert raised.value.field == field

    @pytest.fixture
    def entry_at_the_limit(self) -> CrashoutEntry:
        return replace(SHORT_ENTRY, rant='r' * 5, branch='b' * 5)

    def test_text_at_the_limit_is_kept(self, entry_at_the_limit: CrashoutEntry) -> None:
        record = CrashoutPolicy(entry=entry_at_the_limit, options=self.options).crashout_record(
            MOMENT
        )
        assert (record.rant, record.branch) == ('r' * 5, 'b' * 5)


class TestCrashoutRecord:
    secret = 'ghp_' + 'a' * 36

    @pytest.fixture
    def padded_entry(self) -> CrashoutEntry:
        return create_entry(root_cause='  why \n', corrective_action=' a  b ')

    @pytest.fixture
    def untidy_rant_entry(self) -> CrashoutEntry:
        return create_entry(rant='a  \r\n  b\r\n')

    @pytest.fixture
    def leaked_entry(self) -> CrashoutEntry:
        return replace(create_entry(), root_cause=f'leaked {self.secret}')

    def build_record(self, entry: CrashoutEntry) -> CrashoutRecord:
        return CrashoutPolicy(entry=entry, options=CrashoutOptions()).crashout_record(MOMENT)

    def test_the_root_cause_and_the_action_are_stripped(self, padded_entry: CrashoutEntry) -> None:
        record = self.build_record(padded_entry)
        assert (record.root_cause, record.corrective_action) == ('why', 'a  b')

    def test_the_rant_is_normalized_in_the_record(self, untidy_rant_entry: CrashoutEntry) -> None:
        record = self.build_record(untidy_rant_entry)
        assert record.rant == 'a\n  b'

    def test_a_secret_is_redacted_before_it_is_stored(self, leaked_entry: CrashoutEntry) -> None:
        record = self.build_record(leaked_entry)
        assert self.secret not in record.root_cause

    def test_the_record_carries_the_time_it_was_given(self) -> None:
        assert self.build_record(create_entry()).at == MOMENT

    def test_an_absent_branch_stays_absent(self) -> None:
        assert self.build_record(create_entry(branch=None)).branch is None
