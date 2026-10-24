"""The crashout service over the fakes: add, stats and last."""

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.crashouts import (
    JOURNAL_WINDOW,
    BlankCrashoutFieldError,
    NoFailuresError,
)
from mightymodels_core.primitives import RedactedTextTooLongError

from tests.core.crashouts.crashout_builders import MOMENT, create_entry

if TYPE_CHECKING:
    from mightymodels_core.crashouts import CrashoutEntry

    from tests.core.crashouts.crashout_builders import ServiceHarness

DAY = timedelta(days=1)
ROOT_CAUSE = 'the retry loop drops the connection pool after a timeout'


def refused_entry_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'entry',
        [
            pytest.param(create_entry(failures=()), id='no-failures'),
            pytest.param(create_entry(rant=' '), id='blank-rant'),
            pytest.param(create_entry(rant='r' * 4_001), id='too-long'),
        ],
    )


class TestAdd:
    def test_the_first_crashout_is_number_one(self, service_harness: ServiceHarness) -> None:
        assert service_harness.service.add(create_entry()).number == 1

    def test_the_number_counts_the_crashouts_journaled(
        self, journaled_three: ServiceHarness
    ) -> None:
        assert journaled_three.service.add(create_entry()).number == 4

    def test_a_crashout_is_stored_with_the_time_the_clock_gave(
        self, service_harness: ServiceHarness
    ) -> None:
        service_harness.service.add(create_entry())
        stored = service_harness.crashouts.latest_crashout()
        assert stored is not None
        assert stored.at == MOMENT

    def test_the_root_cause_is_written_to_similarity_under_its_number(
        self, journaled_three: ServiceHarness
    ) -> None:
        journaled_three.service.add(create_entry(root_cause='a new cause'))
        written = journaled_three.similarity.entry('crashout', '#4')
        assert written is not None
        assert written.text == 'a new cause'

    def test_a_root_cause_like_an_earlier_one_is_reported_as_a_duplicate(
        self, service_harness: ServiceHarness
    ) -> None:
        service_harness.service.add(create_entry(root_cause=ROOT_CAUSE))
        journaled = service_harness.service.add(create_entry(root_cause=ROOT_CAUSE))
        assert [duplicate.earlier.reference for duplicate in journaled.duplicates] == ['#1']

    @refused_entry_cases()
    def test_a_refused_entry_writes_nothing(
        self, service_harness: ServiceHarness, entry: CrashoutEntry
    ) -> None:
        with pytest.raises((NoFailuresError, BlankCrashoutFieldError, RedactedTextTooLongError)):
            service_harness.service.add(entry)
        assert service_harness.crashouts.latest_crashout() is None
        assert not service_harness.similarity.ledger.entries


class TestStats:
    def test_an_empty_journal_has_no_stats(self, service_harness: ServiceHarness) -> None:
        assert service_harness.service.stats() is None

    def test_the_counts_name_the_most_common_first(self, journaled_three: ServiceHarness) -> None:
        stats = journaled_three.service.stats()
        assert stats is not None
        assert stats.entries == 3
        assert stats.severities == (('heated', 2), ('full-meltdown', 1))
        assert stats.verdicts == (('deserved', 2), ('split', 1))
        assert stats.barked_back == 1

    def test_the_first_and_last_crashouts_bound_the_journal(
        self, journaled_three: ServiceHarness
    ) -> None:
        stats = journaled_three.service.stats()
        assert stats is not None
        assert (stats.first.at, stats.last.at) == (MOMENT, MOMENT + 2 * DAY)

    def test_every_failure_carries_its_day_verdict_and_severity(
        self, journaled_three: ServiceHarness
    ) -> None:
        stats = journaled_three.service.stats()
        assert stats is not None
        tagged = [(line.day, line.verdict, line.severity, line.failure) for line in stats.failures]
        assert tagged[:3] == [
            (MOMENT.date(), 'deserved', 'heated', 'skipped the tests'),
            (MOMENT.date(), 'deserved', 'heated', 'claimed done'),
            ((MOMENT + DAY).date(), 'deserved', 'full-meltdown', 'skipped the tests again'),
        ]

    def test_the_corrective_actions_collapse_whitespace_and_keep_first_seen_order(
        self, journaled_three: ServiceHarness
    ) -> None:
        stats = journaled_three.service.stats()
        assert stats is not None
        assert stats.corrective_actions == ('run the gate before reporting', 'check the branch')

    def test_a_short_journal_leaves_nothing_out(self, journaled_three: ServiceHarness) -> None:
        stats = journaled_three.service.stats()
        assert stats is not None
        assert not stats.older_left_out

    def test_a_journal_past_the_window_says_older_ones_are_left_out(
        self, overfull_service: ServiceHarness
    ) -> None:
        stats = overfull_service.service.stats()
        assert stats is not None
        assert (stats.entries, stats.older_left_out) == (JOURNAL_WINDOW.rows, True)


class TestLast:
    def test_an_empty_journal_has_no_last_crashout(self, service_harness: ServiceHarness) -> None:
        assert service_harness.service.last() is None

    def test_the_newest_crashout_is_returned(self, journaled_three: ServiceHarness) -> None:
        last = journaled_three.service.last()
        assert last is not None
        assert (last.severity, last.verdict, last.failures) == ('heated', 'split', ('committed',))
