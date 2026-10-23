"""The similarity service over the fakes: search, store a scout report and has a report."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import RedactedTextTooLongError, redact
from mightymodels_core.similarity import (
    IncomingReport,
    SimilarityOptions,
    SimilarityService,
    Written,
)
from mightymodels_core.similarity.tests.fakes import (
    FakeScoutReportRepository,
    FakeSimilarityRepository,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.schemas.scout_reports import Scout

TARGET = 'src/api/client.py'
REPORT = 'the retry loop drops the connection pool after a timeout'
SECRET = 'ghp_' + 'a' * 36


@dataclass(slots=True, kw_only=True, frozen=True)
class ServiceHarness:
    service: SimilarityService
    similarity: FakeSimilarityRepository
    scouts: FakeScoutReportRepository


def create_incoming(
    *, scout: Scout = 'code-scout', target: str = TARGET, report: str = REPORT
) -> IncomingReport:
    return IncomingReport(scout=scout, target=target, report=report)


def create_harness(options: SimilarityOptions) -> ServiceHarness:
    similarity = FakeSimilarityRepository()
    scouts = FakeScoutReportRepository()
    service = SimilarityService(similarity=similarity, scouts=scouts, options=options)
    return ServiceHarness(service=service, similarity=similarity, scouts=scouts)


def too_long_report_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param(create_incoming(target='t' * 6), 'target', id='target'),
        pytest.param(create_incoming(target='t', report='r' * 11), 'report', id='report'),
    ]
    return pytest.mark.parametrize(('incoming', 'field'), cases)


class TestSearch:
    @pytest.fixture
    def harness(self) -> ServiceHarness:
        harness = create_harness(SimilarityOptions())
        harness.similarity.record_all([
            Written(kind='ledger-entry', reference='ENT-1', text=redact(REPORT)),
            Written(kind='crashout', reference='#1', text=redact(REPORT)),
        ])
        return harness

    def test_a_search_without_a_kind_matches_every_kind(self, harness: ServiceHarness) -> None:
        matches = harness.service.search(REPORT, None)
        assert {match.kind for match in matches} == {'ledger-entry', 'crashout'}

    def test_a_search_held_to_a_kind_matches_only_that_kind(self, harness: ServiceHarness) -> None:
        matches = harness.service.search(REPORT, 'crashout')
        assert [match.reference for match in matches] == ['#1']

    def test_a_search_with_no_overlap_matches_nothing(self, harness: ServiceHarness) -> None:
        assert harness.service.search('zebra quartz', None) == []


class TestStoreReport:
    options = SimilarityOptions(name_limit=5, report_limit=10)

    @pytest.fixture
    def harness(self) -> ServiceHarness:
        return create_harness(SimilarityOptions())

    @pytest.fixture
    def limited(self) -> ServiceHarness:
        return create_harness(self.options)

    def test_the_stored_report_gets_the_id_the_repository_gave(
        self, harness: ServiceHarness
    ) -> None:
        first = harness.service.store_report(create_incoming())
        second = harness.service.store_report(create_incoming(target='other.py'))
        assert (first.id, second.id) == (1, 2)

    def test_the_report_is_written_to_similarity_as_a_scout_report_under_its_id(
        self, harness: ServiceHarness
    ) -> None:
        stored = harness.service.store_report(create_incoming())
        written = harness.similarity.entry('scout-report', str(stored.id))
        assert written is not None
        assert written.text == REPORT

    def test_a_report_like_an_earlier_one_is_reported_as_a_duplicate(
        self, harness: ServiceHarness
    ) -> None:
        harness.service.store_report(create_incoming())
        stored = harness.service.store_report(create_incoming(target='other.py'))
        assert [duplicate.earlier.reference for duplicate in stored.duplicates] == ['1']

    def test_a_secret_is_redacted_in_the_target_and_the_report(
        self, harness: ServiceHarness
    ) -> None:
        harness.service.store_report(create_incoming(target=f'a {SECRET}', report=f'b {SECRET}'))
        stored = harness.scouts.ledger.reports[0]
        assert SECRET not in stored.target
        assert SECRET not in stored.report

    def test_text_at_the_limits_is_stored(self, limited: ServiceHarness) -> None:
        stored = limited.service.store_report(create_incoming(target='t' * 5, report='r' * 10))
        assert stored.id == 1

    @too_long_report_cases()
    def test_text_redaction_leaves_too_long_refuses_the_report_and_writes_nothing(
        self, limited: ServiceHarness, incoming: IncomingReport, field: str
    ) -> None:
        with pytest.raises(RedactedTextTooLongError) as raised:
            limited.service.store_report(incoming)
        assert raised.value.field == field
        assert not limited.scouts.ledger.reports
        assert not limited.similarity.ledger.entries


class TestHasReportOf:
    @pytest.fixture
    def stored(self) -> ServiceHarness:
        harness = create_harness(SimilarityOptions())
        harness.service.store_report(create_incoming(target=f'file {SECRET}'))
        return harness

    def test_a_report_is_known_by_its_scout_and_target(self, stored: ServiceHarness) -> None:
        assert stored.service.has_report_of(create_incoming(target=f'file {SECRET}'))

    def test_the_target_is_redacted_before_it_is_compared(self, stored: ServiceHarness) -> None:
        other_secret = 'ghp_' + 'b' * 36
        assert stored.service.has_report_of(create_incoming(target=f'file {other_secret}'))

    def test_another_scout_has_no_report_of_the_target(self, stored: ServiceHarness) -> None:
        assert not stored.service.has_report_of(
            create_incoming(scout='web-scout', target=f'file {SECRET}')
        )

    def test_another_target_has_no_report(self, stored: ServiceHarness) -> None:
        assert not stored.service.has_report_of(create_incoming(target='other.py'))
