from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import (
    DuplicateRowError,
    MissingParentError,
)
from mightymodels_core.schemas.reviews import (
    DELETE_REVIEW_DISPOSITIONS,
    DELETE_REVIEW_OUTCOMES,
    LATEST_REVIEW_RUN_OF_TICKET,
    LATEST_REVIEW_RUNS,
    RECORD_REVIEW_MODELS,
    RECORD_REVIEW_RUN,
    REVIEW_DISPOSITION_COUNT,
    REVIEW_DISPOSITIONS_OF_RUN,
    REVIEW_FINDING_COUNT,
    REVIEW_FINDINGS_OF_RUN,
    REVIEW_OUTCOME_COUNT,
    REVIEW_OUTCOMES_OF_RUN,
    REVIEW_RUN,
    UPSERT_REVIEW_DISPOSITION,
    UPSERT_REVIEW_FINDING,
    UPSERT_REVIEW_OUTCOME,
    Decision,
    Depth,
    Emphasis,
    EvidenceKind,
    FindingKeysParams,
    FindingKind,
    LatestReviewRunsParams,
    RecordReviewModelsParams,
    RecordReviewRunParams,
    Result,
    ReviewRunParams,
    RunLimitParams,
    RunParams,
    Scope,
    Severity,
    TicketReviewRunParams,
    UpsertReviewDispositionParams,
    UpsertReviewFindingParams,
    UpsertReviewOutcomeParams,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Database

pytestmark = pytest.mark.integration

RECORDED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
LIMIT = 100


def run(repository_id: int, run_key: str, ticket_key: str | None = None) -> RecordReviewRunParams:
    return RecordReviewRunParams(
        repository_id=repository_id,
        run_key=run_key,
        ticket_key=ticket_key,
        scope=Scope.BRANCH,
        base='main',
        head='abc1234',
        depth=Depth.STANDARD,
        emphasis=Emphasis.BALANCED,
        weights={'merge-vader': 0.6, 'uncle-bob': 0.4},
        personas=['merge-vader', 'uncle-bob'],
        models={'merge-vader': 'opus', 'uncle-bob': None},
        created_at=RECORDED_AT,
    )


def finding(
    review_run_id: int, finding_key: str, title: str = 'a title'
) -> UpsertReviewFindingParams:
    return UpsertReviewFindingParams(
        review_run_id=review_run_id,
        finding_key=finding_key,
        sources=['merge-vader'],
        severity=Severity.HIGH,
        kind=FindingKind.DEFECT,
        security=True,
        title=title,
        location='src/app.py:1',
        fix='fix it',
        verify='run it',
        evidence_kind=EvidenceKind.METRIC,
        evidence_cite='churn',
        conflict=None,
    )


def disposition(
    review_run_id: int, finding_key: str, decision: Decision = Decision.FIX
) -> UpsertReviewDispositionParams:
    return UpsertReviewDispositionParams(
        review_run_id=review_run_id,
        finding_key=finding_key,
        decision=decision,
        reason='because',
        by='user',
        at=RECORDED_AT,
    )


def outcome(
    review_run_id: int, finding_key: str, result: Result = Result.FIXED
) -> UpsertReviewOutcomeParams:
    return UpsertReviewOutcomeParams(
        review_run_id=review_run_id,
        finding_key=finding_key,
        result=result,
        commit='deadbee',
        reason='done',
        at=RECORDED_AT,
    )


def record(database: Database, params: RecordReviewRunParams) -> int:
    with database.write() as unit:
        recorded = unit.one(RECORD_REVIEW_RUN, params)
    assert recorded is not None
    return recorded.id


def finding_keys(database: Database, review_run_id: int) -> list[str]:
    with database.read() as unit:
        rows = unit.all(
            REVIEW_FINDINGS_OF_RUN, RunLimitParams(review_run_id=review_run_id, limit=LIMIT)
        )
    return [row.finding_key for row in rows]


class TestReviewRuns:
    def test_a_run_reads_back_every_column(self, database: Database, repository_id: int) -> None:
        recorded = record(database, run(repository_id, 'r-1', 'staged'))

        with database.read() as unit:
            row = unit.one(REVIEW_RUN, ReviewRunParams(repository_id=repository_id, run_key='r-1'))

        assert row is not None
        assert row.id == recorded
        assert row.run_key == 'r-1'
        assert row.ticket_key == 'staged'
        assert row.scope is Scope.BRANCH
        assert row.base == 'main'
        assert row.head == 'abc1234'
        assert row.depth is Depth.STANDARD
        assert row.emphasis is Emphasis.BALANCED
        assert row.weights == {'merge-vader': 0.6, 'uncle-bob': 0.4}
        assert row.personas == ['merge-vader', 'uncle-bob']
        assert row.models == {'merge-vader': 'opus', 'uncle-bob': None}
        assert row.created_at == RECORDED_AT

    def test_an_unknown_run_reads_as_none(self, database: Database, repository_id: int) -> None:
        with database.read() as unit:
            row = unit.one(REVIEW_RUN, ReviewRunParams(repository_id=repository_id, run_key='r-1'))

        assert row is None

    def test_a_run_key_is_unique_within_a_repository(
        self, database: Database, repository_id: int
    ) -> None:
        record(database, run(repository_id, 'r-1'))

        with pytest.raises(DuplicateRowError):
            record(database, run(repository_id, 'r-1'))

    def test_a_run_needs_a_repository(self, database: Database) -> None:
        with pytest.raises(MissingParentError):
            record(database, run(999, 'r-1'))

    def test_the_latest_runs_are_newest_first_and_limited(
        self, database: Database, repository_id: int
    ) -> None:
        for run_key in ('r-1', 'r-2', 'r-3'):
            record(database, run(repository_id, run_key))

        with database.read() as unit:
            latest = unit.all(
                LATEST_REVIEW_RUNS, LatestReviewRunsParams(repository_id=repository_id, limit=2)
            )

        assert [row.run_key for row in latest] == ['r-3', 'r-2']

    def test_the_latest_run_of_a_ticket_ignores_other_tickets(
        self, database: Database, repository_id: int
    ) -> None:
        record(database, run(repository_id, 'r-1', 'staged'))
        record(database, run(repository_id, 'r-2', 'staged'))
        record(database, run(repository_id, 'r-3', 'other'))

        with database.read() as unit:
            latest = unit.one(
                LATEST_REVIEW_RUN_OF_TICKET,
                TicketReviewRunParams(repository_id=repository_id, ticket_key='staged'),
            )
            none = unit.one(
                LATEST_REVIEW_RUN_OF_TICKET,
                TicketReviewRunParams(repository_id=repository_id, ticket_key='absent'),
            )

        assert latest is not None
        assert latest.run_key == 'r-2'
        assert none is None

    def test_recording_models_replaces_the_models_of_that_run_only(
        self, database: Database, repository_id: int
    ) -> None:
        record(database, run(repository_id, 'r-1'))
        record(database, run(repository_id, 'r-2'))

        with database.write() as unit:
            changed = unit.run(
                RECORD_REVIEW_MODELS,
                RecordReviewModelsParams(
                    repository_id=repository_id, run_key='r-1', models={'uncle-bob': 'sonnet'}
                ),
            )
        with database.read() as unit:
            first = unit.one(
                REVIEW_RUN, ReviewRunParams(repository_id=repository_id, run_key='r-1')
            )
            second = unit.one(
                REVIEW_RUN, ReviewRunParams(repository_id=repository_id, run_key='r-2')
            )

        assert changed == 1
        assert first is not None
        assert first.models == {'uncle-bob': 'sonnet'}
        assert second is not None
        assert second.models == {'merge-vader': 'opus', 'uncle-bob': None}


class TestReviewFindings:
    def test_a_finding_reads_back_every_column(
        self, database: Database, repository_id: int
    ) -> None:
        run_id = record(database, run(repository_id, 'r-1'))
        with database.write() as unit:
            unit.run_many(UPSERT_REVIEW_FINDING, [finding(run_id, 'F1')])

        with database.read() as unit:
            rows = unit.all(
                REVIEW_FINDINGS_OF_RUN, RunLimitParams(review_run_id=run_id, limit=LIMIT)
            )

        assert len(rows) == 1
        row = rows[0]
        assert row.finding_key == 'F1'
        assert row.sources == ['merge-vader']
        assert row.severity is Severity.HIGH
        assert row.kind is FindingKind.DEFECT
        assert row.security is True
        assert row.title == 'a title'
        assert row.location == 'src/app.py:1'
        assert row.fix == 'fix it'
        assert row.verify == 'run it'
        assert row.evidence_kind is EvidenceKind.METRIC
        assert row.evidence_cite == 'churn'
        assert row.conflict is None

    def test_findings_order_by_key_length_then_key(
        self, database: Database, repository_id: int
    ) -> None:
        run_id = record(database, run(repository_id, 'r-1'))
        with database.write() as unit:
            unit.run_many(
                UPSERT_REVIEW_FINDING,
                [finding(run_id, key) for key in ('F10', 'F2', 'F1', 'F9')],
            )

        assert finding_keys(database, run_id) == ['F1', 'F2', 'F9', 'F10']

    def test_upserting_a_finding_replaces_it_and_the_count_holds(
        self, database: Database, repository_id: int
    ) -> None:
        run_id = record(database, run(repository_id, 'r-1'))
        with database.write() as unit:
            unit.run_many(UPSERT_REVIEW_FINDING, [finding(run_id, 'F1', 'old')])
        with database.write() as unit:
            unit.run_many(UPSERT_REVIEW_FINDING, [finding(run_id, 'F1', 'new')])

        with database.read() as unit:
            rows = unit.all(
                REVIEW_FINDINGS_OF_RUN, RunLimitParams(review_run_id=run_id, limit=LIMIT)
            )
            count = unit.one(REVIEW_FINDING_COUNT, RunParams(review_run_id=run_id))

        assert [row.title for row in rows] == ['new']
        assert count is not None
        assert count.count == 1

    def test_findings_are_scoped_to_their_run(self, database: Database, repository_id: int) -> None:
        first = record(database, run(repository_id, 'r-1'))
        second = record(database, run(repository_id, 'r-2'))
        with database.write() as unit:
            unit.run_many(UPSERT_REVIEW_FINDING, [finding(first, 'F1'), finding(second, 'F1')])

        assert finding_keys(database, first) == ['F1']
        assert finding_keys(database, second) == ['F1']

    def test_a_finding_needs_a_run(self, database: Database) -> None:
        with pytest.raises(MissingParentError), database.write() as unit:
            unit.run_many(UPSERT_REVIEW_FINDING, [finding(999, 'F1')])


class TestReviewDecisions:
    def decided_run(self, database: Database, repository_id: int) -> int:
        run_id = record(database, run(repository_id, 'r-1'))
        with database.write() as unit:
            unit.run_many(UPSERT_REVIEW_FINDING, [finding(run_id, 'F1'), finding(run_id, 'F2')])
            unit.run_many(
                UPSERT_REVIEW_DISPOSITION, [disposition(run_id, 'F1'), disposition(run_id, 'F2')]
            )
            unit.run_many(UPSERT_REVIEW_OUTCOME, [outcome(run_id, 'F1')])
        return run_id

    def test_dispositions_read_back_every_column_in_finding_order(
        self, database: Database, repository_id: int
    ) -> None:
        run_id = self.decided_run(database, repository_id)

        with database.read() as unit:
            rows = unit.all(
                REVIEW_DISPOSITIONS_OF_RUN, RunLimitParams(review_run_id=run_id, limit=LIMIT)
            )
            count = unit.one(REVIEW_DISPOSITION_COUNT, RunParams(review_run_id=run_id))

        assert [row.finding_key for row in rows] == ['F1', 'F2']
        assert rows[0].decision is Decision.FIX
        assert rows[0].reason == 'because'
        assert rows[0].by == 'user'
        assert rows[0].at == RECORDED_AT
        assert count is not None
        assert count.count == 2

    def test_outcomes_read_back_every_column(self, database: Database, repository_id: int) -> None:
        run_id = self.decided_run(database, repository_id)

        with database.read() as unit:
            rows = unit.all(
                REVIEW_OUTCOMES_OF_RUN, RunLimitParams(review_run_id=run_id, limit=LIMIT)
            )
            count = unit.one(REVIEW_OUTCOME_COUNT, RunParams(review_run_id=run_id))

        assert len(rows) == 1
        assert rows[0].finding_key == 'F1'
        assert rows[0].result is Result.FIXED
        assert rows[0].commit == 'deadbee'
        assert rows[0].reason == 'done'
        assert rows[0].at == RECORDED_AT
        assert count is not None
        assert count.count == 1

    def test_deciding_again_replaces_the_decision(
        self, database: Database, repository_id: int
    ) -> None:
        run_id = self.decided_run(database, repository_id)
        with database.write() as unit:
            unit.run_many(UPSERT_REVIEW_DISPOSITION, [disposition(run_id, 'F1', Decision.DISMISS)])
            unit.run_many(UPSERT_REVIEW_OUTCOME, [outcome(run_id, 'F1', Result.BLOCKED)])

        with database.read() as unit:
            dispositions = unit.all(
                REVIEW_DISPOSITIONS_OF_RUN, RunLimitParams(review_run_id=run_id, limit=LIMIT)
            )
            outcomes = unit.all(
                REVIEW_OUTCOMES_OF_RUN, RunLimitParams(review_run_id=run_id, limit=LIMIT)
            )

        assert [row.decision for row in dispositions] == [Decision.DISMISS, Decision.FIX]
        assert [row.result for row in outcomes] == [Result.BLOCKED]

    def test_a_decision_without_its_finding_or_disposition_stores_nothing(
        self, database: Database, repository_id: int
    ) -> None:
        run_id = self.decided_run(database, repository_id)
        with database.write() as unit:
            decided = unit.run_many(UPSERT_REVIEW_DISPOSITION, [disposition(run_id, 'F9')])
            unit.run_many(UPSERT_REVIEW_FINDING, [finding(run_id, 'F3')])
            resolved = unit.run_many(UPSERT_REVIEW_OUTCOME, [outcome(run_id, 'F3')])

        assert decided == 0
        assert resolved == 0

    def test_reopening_deletes_only_the_named_findings(
        self, database: Database, repository_id: int
    ) -> None:
        run_id = self.decided_run(database, repository_id)
        keys = FindingKeysParams(review_run_id=run_id, finding_keys=['F1'])

        with database.write() as unit:
            reopened_outcomes = unit.run(DELETE_REVIEW_OUTCOMES, keys)
            reopened_dispositions = unit.run(DELETE_REVIEW_DISPOSITIONS, keys)
        with database.read() as unit:
            dispositions = unit.all(
                REVIEW_DISPOSITIONS_OF_RUN, RunLimitParams(review_run_id=run_id, limit=LIMIT)
            )
            outcomes = unit.all(
                REVIEW_OUTCOMES_OF_RUN, RunLimitParams(review_run_id=run_id, limit=LIMIT)
            )

        assert reopened_outcomes == 1
        assert reopened_dispositions == 1
        assert [row.finding_key for row in dispositions] == ['F2']
        assert outcomes == []

    def test_deleting_an_outcome_keeps_its_disposition(
        self, database: Database, repository_id: int
    ) -> None:
        run_id = self.decided_run(database, repository_id)

        with database.write() as unit:
            unit.run(
                DELETE_REVIEW_OUTCOMES, FindingKeysParams(review_run_id=run_id, finding_keys=['F1'])
            )
        with database.read() as unit:
            count = unit.one(REVIEW_DISPOSITION_COUNT, RunParams(review_run_id=run_id))

        assert count is not None
        assert count.count == 2
