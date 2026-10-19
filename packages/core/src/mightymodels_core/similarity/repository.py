"""The seams under the similarity services: near-duplicate search over stored text, and the scout
reports already spooled.

`record` stores the text under its kind and reference, replacing what that pair held, and returns
the closest earlier entry whose overlap reaches the match threshold, or `None`. The entry itself is
never its own duplicate. `entry` reads back what `record` stored. `add_report` returns the id of
the stored report; it does not search for duplicates, which the similarity service composes from
the two repositories.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mightymodels_core.schemas.similarity import SimilarityKind
    from mightymodels_core.similarity.records import Duplicate, Match, ScoutReport, Written


@runtime_checkable
class SimilarityRepository(Protocol):
    def search(self, query: str, *, kind: SimilarityKind | None) -> list[Match]: ...

    def entry(self, kind: SimilarityKind, reference: str) -> Written | None: ...

    def record(self, written: Written) -> Duplicate | None: ...

    def record_all(self, writes: Iterable[Written]) -> list[Duplicate]: ...


@runtime_checkable
class ScoutReportRepository(Protocol):
    def has_report(self, report: ScoutReport) -> bool: ...

    def add_report(self, report: ScoutReport) -> int: ...
