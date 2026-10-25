"""The scout report repository contract against the fake."""

from mightymodels_core.similarity import ScoutReportRepository

from tests.core.similarity.fakes import FakeScoutReportRepository
from tests.core.similarity.scout_report_repository_suite import ScoutReportRepositoryContract


class TestFakeScoutReportRepository(ScoutReportRepositoryContract):
    pass


class TestFakeImplementation:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeScoutReportRepository(), ScoutReportRepository)
