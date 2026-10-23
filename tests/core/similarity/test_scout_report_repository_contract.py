"""Every scout report repository case runs against the sqlite store and the fake."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.similarity import ScoutReportRepository
from mightymodels_core.similarity.tests.fakes import FakeScoutReportRepository

from .conftest import STORED_TARGET, create_scout_report

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.similarity import ScoutReport

    from .conftest import SimilarityHarness


@dataclass(slots=True, kw_only=True, frozen=True)
class LookupCase:
    name: str
    report: ScoutReport
    held: bool

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def scout_report_lookup_cases() -> pytest.MarkDecorator:
    same = LookupCase(name='same-scout-and-target', report=create_scout_report(), held=True)
    other_body = LookupCase(
        name='other-report-body', report=create_scout_report(report='it is sync'), held=True
    )
    other_scout = LookupCase(
        name='other-scout', report=create_scout_report(scout='web-scout'), held=False
    )
    other_target = LookupCase(
        name='other-target', report=create_scout_report('src/api/server.py'), held=False
    )
    return pytest.mark.parametrize(
        'case', [same.param, other_body.param, other_scout.param, other_target.param]
    )


class TestImplementations:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeScoutReportRepository(), ScoutReportRepository)

    def test_repository_satisfies_the_protocol(self, harness: SimilarityHarness) -> None:
        assert isinstance(harness.scouts, ScoutReportRepository)


class TestHasReport:
    def test_empty_repository_holds_no_report(self, harness: SimilarityHarness) -> None:
        assert not harness.scouts.has_report(create_scout_report())

    @scout_report_lookup_cases()
    def test_report_is_held_by_scout_and_target(
        self, stocked: SimilarityHarness, case: LookupCase
    ) -> None:
        assert stocked.scouts.has_report(case.report) is case.held


class TestAddReport:
    def test_added_report_is_held(self, harness: SimilarityHarness) -> None:
        harness.scouts.add_report(create_scout_report())

        assert harness.scouts.has_report(create_scout_report(STORED_TARGET))

    def test_each_added_report_gets_its_own_id(self, harness: SimilarityHarness) -> None:
        first = harness.scouts.add_report(create_scout_report())
        second = harness.scouts.add_report(create_scout_report())

        assert first != second

    def test_adding_a_report_records_no_similarity_entry(self, stocked: SimilarityHarness) -> None:
        assert stocked.similarity.entry('scout-report', '1') is None
