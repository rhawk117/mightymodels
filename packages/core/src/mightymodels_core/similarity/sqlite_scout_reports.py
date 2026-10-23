"""The scout report repository over a core unit."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.schemas.scout_reports import (
    ADD_SCOUT_REPORT,
    SCOUT_REPORT_OF_TARGET,
    AddScoutReportParams,
    ScoutReportTargetParams,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Unit
    from mightymodels_core.similarity.records import ScoutReport


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteScoutReportRepository:
    unit: Unit
    repository_id: int

    def has_report(self, report: ScoutReport) -> bool:
        params = ScoutReportTargetParams(
            repository_id=self.repository_id, scout=report.scout, target=report.target
        )
        return self.unit.one(SCOUT_REPORT_OF_TARGET, params) is not None

    def add_report(self, report: ScoutReport) -> int:
        params = AddScoutReportParams(
            repository_id=self.repository_id,
            scout=report.scout,
            target=report.target,
            report=report.report,
        )
        (added,) = self.unit.all(ADD_SCOUT_REPORT, params)
        return added.id
