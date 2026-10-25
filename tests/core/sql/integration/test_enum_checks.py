import re
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING, get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st
from mightymodels_core.database import ConnectionOptions, open_database
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

    from mightymodels_core.database import DatabaseSpec

STRING_CHECK_PAIRS = (
    ('tickets', 'ck_tickets_status', TicketStatus),
    ('tickets', 'ck_tickets_scope', TicketScope),
    ('ledger_entries', 'ck_ledger_entries_kind', EntryKind),
    ('ledger_entries', 'ck_ledger_entries_source', EntrySource),
    ('tasks', 'ck_tasks_status', TaskStatus),
    ('task_attempts', 'ck_task_attempts_worker', Worker),
    ('task_attempts', 'ck_task_attempts_mode', ArchitectMode),
    ('task_transitions', 'ck_task_transitions_before', TaskStatus),
    ('task_transitions', 'ck_task_transitions_after', TaskStatus),
    ('receipts', 'ck_receipts_outcome', Outcome),
    ('receipts', 'ck_receipts_phase', Phase),
    ('review_runs', 'ck_review_runs_scope', Scope),
    ('review_runs', 'ck_review_runs_depth', Depth),
    ('review_runs', 'ck_review_runs_emphasis', Emphasis),
    ('review_findings', 'ck_review_findings_severity', StoredSeverity),
    ('review_findings', 'ck_review_findings_kind', FindingKind),
    ('review_findings', 'ck_review_findings_evidence_kind', EvidenceKind),
    ('review_dispositions', 'ck_review_dispositions_decision', Decision),
    ('review_outcomes', 'ck_review_outcomes_result', Result),
    ('crashouts', 'ck_crashouts_severity', CrashoutSeverity),
    ('crashouts', 'ck_crashouts_verdict', Verdict),
    ('similarity', 'ck_similarity_kind', SimilarityKind),
    ('scout_reports', 'ck_scout_reports_scout', Scout),
)


def check_values(connection: sqlite3.Connection, table: str, constraint: str) -> set[str]:
    row = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    assert row is not None, f'table {table} is missing from the schema'
    match = re.search(rf'CONSTRAINT\s+{constraint}\s+CHECK\s*\(\s*\w+\s+IN\s*\(([^)]*)\)', row[0])
    assert match is not None, f'{constraint} is not an IN check on {table}'
    return set(re.findall(r"'([^']*)'", match.group(1)))


class TestCheckLists:
    check_pairs = st.sampled_from(STRING_CHECK_PAIRS)

    def inspect_check_values(
        self,
        tmp_path_factory: pytest.TempPathFactory,
        database_spec: DatabaseSpec,
        table: str,
        constraint: str,
    ) -> set[str]:
        path = tmp_path_factory.mktemp('checks').joinpath('mightymodels.db')
        open_database(path, database_spec, ConnectionOptions()).close()
        with closing(sqlite3.connect(path)) as connection:
            return check_values(connection, table, constraint)

    @given(pair=check_pairs)
    def test_check_list_matches_alias(
        self,
        tmp_path_factory: pytest.TempPathFactory,
        database_spec: DatabaseSpec,
        pair: tuple[str, str, TypeAliasType],
    ) -> None:
        table, constraint, alias = pair
        values = self.inspect_check_values(tmp_path_factory, database_spec, table, constraint)
        assert values == set(get_args(alias.__value__))


INSERT_FINDING = (
    'INSERT INTO review_findings'
    ' (review_run_id, finding_key, sources, severity, title, location, fix, verify)'
    " VALUES (1, 'F1', '[]', ?, 't', 'a.py:1', 'f', 'v')"
)


def test_blocker_severity_is_refused(schema_inspection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError, match='ck_review_findings_severity'):
        schema_inspection.execute(INSERT_FINDING, ('Blocker',))
