import re
import sqlite3
from typing import TYPE_CHECKING, get_args

import pytest
from mightymodels_core.schemas.contract import Outcome, Phase
from mightymodels_core.schemas.crashouts import CrashoutSeverity, Verdict
from mightymodels_core.schemas.investigations import EntryKind, EntrySource
from mightymodels_core.schemas.reviews import (
    Decision,
    Depth,
    Emphasis,
    EvidenceKind,
    FindingKind,
    Result,
    Scope,
    StoredSeverity,
)
from mightymodels_core.schemas.scout_reports import Scout
from mightymodels_core.schemas.similarity import SimilarityKind
from mightymodels_core.schemas.tasks import ArchitectMode, TaskStatus, Worker
from mightymodels_core.schemas.tickets import TicketScope, TicketStatus

if TYPE_CHECKING:
    from typing import TypeAliasType

pytestmark = pytest.mark.integration

STRING_CHECK_PAIRS = (
    pytest.param('tickets', 'ck_tickets_status', TicketStatus, id='tickets.status'),
    pytest.param('tickets', 'ck_tickets_scope', TicketScope, id='tickets.scope'),
    pytest.param('ledger_entries', 'ck_ledger_entries_kind', EntryKind, id='ledger_entries.kind'),
    pytest.param(
        'ledger_entries', 'ck_ledger_entries_source', EntrySource, id='ledger_entries.source'
    ),
    pytest.param('tasks', 'ck_tasks_status', TaskStatus, id='tasks.status'),
    pytest.param('task_attempts', 'ck_task_attempts_worker', Worker, id='task_attempts.worker'),
    pytest.param('task_attempts', 'ck_task_attempts_mode', ArchitectMode, id='task_attempts.mode'),
    pytest.param(
        'task_transitions', 'ck_task_transitions_before', TaskStatus, id='task_transitions.before'
    ),
    pytest.param(
        'task_transitions', 'ck_task_transitions_after', TaskStatus, id='task_transitions.after'
    ),
    pytest.param('receipts', 'ck_receipts_outcome', Outcome, id='receipts.outcome'),
    pytest.param('receipts', 'ck_receipts_phase', Phase, id='receipts.phase'),
    pytest.param('review_runs', 'ck_review_runs_scope', Scope, id='review_runs.scope'),
    pytest.param('review_runs', 'ck_review_runs_depth', Depth, id='review_runs.depth'),
    pytest.param('review_runs', 'ck_review_runs_emphasis', Emphasis, id='review_runs.emphasis'),
    pytest.param(
        'review_findings',
        'ck_review_findings_severity',
        StoredSeverity,
        id='review_findings.severity',
    ),
    pytest.param(
        'review_findings', 'ck_review_findings_kind', FindingKind, id='review_findings.kind'
    ),
    pytest.param(
        'review_findings',
        'ck_review_findings_evidence_kind',
        EvidenceKind,
        id='review_findings.evidence_kind',
    ),
    pytest.param(
        'review_dispositions',
        'ck_review_dispositions_decision',
        Decision,
        id='review_dispositions.decision',
    ),
    pytest.param(
        'review_outcomes', 'ck_review_outcomes_result', Result, id='review_outcomes.result'
    ),
    pytest.param('crashouts', 'ck_crashouts_severity', CrashoutSeverity, id='crashouts.severity'),
    pytest.param('crashouts', 'ck_crashouts_verdict', Verdict, id='crashouts.verdict'),
    pytest.param('similarity', 'ck_similarity_kind', SimilarityKind, id='similarity.kind'),
    pytest.param('scout_reports', 'ck_scout_reports_scout', Scout, id='scout_reports.scout'),
)


def check_values(connection: sqlite3.Connection, table: str, constraint: str) -> set[str]:
    row = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    assert row is not None, f'table {table} is missing from the schema'
    match = re.search(rf'CONSTRAINT\s+{constraint}\s+CHECK\s*\(\s*\w+\s+IN\s*\(([^)]*)\)', row[0])
    assert match is not None, f'{constraint} is not an IN check on {table}'
    return set(re.findall(r"'([^']*)'", match.group(1)))


@pytest.mark.parametrize(('table', 'constraint', 'alias'), STRING_CHECK_PAIRS)
def test_check_list_matches_alias(
    schema_inspection: sqlite3.Connection, table: str, constraint: str, alias: TypeAliasType
) -> None:
    assert check_values(schema_inspection, table, constraint) == set(get_args(alias.__value__))


INSERT_FINDING = (
    'INSERT INTO review_findings'
    ' (review_run_id, finding_key, sources, severity, title, location, fix, verify)'
    " VALUES (1, 'F1', '[]', ?, 't', 'a.py:1', 'f', 'v')"
)


def test_blocker_severity_is_refused(schema_inspection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError, match='ck_review_findings_severity'):
        schema_inspection.execute(INSERT_FINDING, ('Blocker',))
