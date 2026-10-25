"""The seams under the review services: review runs with their findings, and the decisions on them.

`findings` refuses to answer from part of the rows. `record_findings` stores every finding or none:
a batch that leaves the run with more findings than one read returns is refused with
`WriteLimitError`, and a run that was never started with `RunNotFoundError`. `record_run` refuses a
run key the repository already holds with `RunExistsError`. `record_dispositions` stores every
disposition or none and refuses a finding the run does not hold with `UnknownFindingError`;
`record_outcome` refuses a finding with no disposition with `UndecidedFindingError`. `reopen`
drops the disposition and the outcome of each finding it is given.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence

    from mightymodels_core.primitives import Latest, RunId, Slug
    from mightymodels_core.reviews.records import (
        DecidedFinding,
        FindingRecord,
        ResolvedFinding,
        ReviewRunRecord,
    )


@runtime_checkable
class ReviewRepository(Protocol):
    def run(self, run: RunId) -> ReviewRunRecord | None: ...

    def started_run(self, run: RunId) -> ReviewRunRecord: ...

    def latest_runs(self) -> Latest[ReviewRunRecord]: ...

    def latest_run(self, slug: Slug) -> ReviewRunRecord | None: ...

    def findings(self, run: RunId) -> list[FindingRecord]: ...

    def record_run(self, run: ReviewRunRecord) -> None: ...

    def record_models(self, run: RunId, models: Mapping[str, str | None]) -> None: ...

    def record_findings(self, run: RunId, findings: Sequence[FindingRecord]) -> None: ...


@runtime_checkable
class ReviewDecisionRepository(Protocol):
    def dispositions(self, run: RunId) -> list[DecidedFinding]: ...

    def outcomes(self, run: RunId) -> list[ResolvedFinding]: ...

    def record_dispositions(self, run: RunId, decided: Sequence[DecidedFinding]) -> None: ...

    def record_outcome(self, run: RunId, resolved: ResolvedFinding) -> None: ...

    def reopen(self, run: RunId, finding_keys: Collection[str]) -> None: ...
