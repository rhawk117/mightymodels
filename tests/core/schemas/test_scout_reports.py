from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import MissingParentError
from mightymodels_core.schemas.scout_reports import (
    ADD_SCOUT_REPORT,
    SCOUT_REPORT_OF_TARGET,
    AddScoutReportParams,
    ScoutReportTargetParams,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Database
    from mightymodels_core.schemas.scout_reports import Scout

pytestmark = pytest.mark.integration


def report(repository_id: int, scout: Scout, target: str) -> AddScoutReportParams:
    return AddScoutReportParams(
        repository_id=repository_id, scout=scout, target=target, report='what the scout found'
    )


def add(database: Database, params: AddScoutReportParams) -> int:
    with database.write() as unit:
        added = unit.one(ADD_SCOUT_REPORT, params)
    assert added is not None
    return added.id


class TestScoutReports:
    def test_a_report_is_found_by_its_repository_scout_and_target(
        self, database: Database, repository_id: int
    ) -> None:
        added = add(database, report(repository_id, 'code-scout', 'src/app.py'))

        with database.read() as unit:
            found = unit.one(
                SCOUT_REPORT_OF_TARGET,
                ScoutReportTargetParams(
                    repository_id=repository_id, scout='code-scout', target='src/app.py'
                ),
            )

        assert found is not None
        assert found.id == added

    def test_a_report_for_another_scout_or_target_is_not_found(
        self, database: Database, repository_id: int
    ) -> None:
        add(database, report(repository_id, 'code-scout', 'src/app.py'))

        with database.read() as unit:
            other_scout = unit.one(
                SCOUT_REPORT_OF_TARGET,
                ScoutReportTargetParams(
                    repository_id=repository_id, scout='web-scout', target='src/app.py'
                ),
            )
            other_target = unit.one(
                SCOUT_REPORT_OF_TARGET,
                ScoutReportTargetParams(
                    repository_id=repository_id, scout='code-scout', target='src/other.py'
                ),
            )
            other_repository = unit.one(
                SCOUT_REPORT_OF_TARGET,
                ScoutReportTargetParams(
                    repository_id=repository_id + 1, scout='code-scout', target='src/app.py'
                ),
            )

        assert other_scout is None
        assert other_target is None
        assert other_repository is None

    def test_the_same_target_can_be_reported_again(
        self, database: Database, repository_id: int
    ) -> None:
        first = add(database, report(repository_id, 'code-scout', 'src/app.py'))
        second = add(database, report(repository_id, 'code-scout', 'src/app.py'))

        assert second > first

    def test_a_report_needs_a_repository(self, database: Database) -> None:
        with pytest.raises(MissingParentError), database.write() as unit:
            unit.one(ADD_SCOUT_REPORT, report(999, 'code-scout', 'src/app.py'))
