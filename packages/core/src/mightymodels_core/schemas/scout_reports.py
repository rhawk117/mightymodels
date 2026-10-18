"""The reports a scout has returned for a target."""

from enum import StrEnum
from typing import TYPE_CHECKING

from msgspec import Struct

from mightymodels_core.database import Query

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration


class Scout(StrEnum):
    CODE_SCOUT = 'code-scout'
    WEB_SCOUT = 'web-scout'


class AddScoutReportParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    scout: Scout
    target: str
    report: str


class ScoutReportTargetParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    scout: Scout
    target: str


class ScoutReportIdRow(Struct, frozen=True, kw_only=True, gc=False):
    id: int


ADD_SCOUT_REPORT = Query(name='add_scout_report', params=AddScoutReportParams, row=ScoutReportIdRow)
SCOUT_REPORT_OF_TARGET = Query(
    name='scout_report_of_target', params=ScoutReportTargetParams, row=ScoutReportIdRow
)

DECLARATIONS: tuple[Declaration, ...] = (ADD_SCOUT_REPORT, SCOUT_REPORT_OF_TARGET)
