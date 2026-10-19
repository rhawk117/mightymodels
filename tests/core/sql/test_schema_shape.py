import re
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, SchemaVersionError, open_database

from .conftest import SCHEMA

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.database import DatabaseSpec

pytestmark = pytest.mark.integration

TABLES = frozenset({
    'repositories',
    'tickets',
    'ticket_investigations',
    'investigations',
    'ledger_entries',
    'tasks',
    'task_attempts',
    'task_failed_fixes',
    'task_transitions',
    'contract_commands',
    'receipts',
    'review_runs',
    'review_findings',
    'review_dispositions',
    'review_outcomes',
    'crashouts',
    'similarity',
    'scout_reports',
    'closings',
})

CONSTRAINT_PREFIXES = {
    'PRIMARY KEY': 'pk_',
    'FOREIGN KEY': 'fk_',
    'UNIQUE': 'uq_',
    'CHECK': 'ck_',
}


def strip_comments(script: str) -> str:
    return re.sub(r'--[^\n]*', '', script)


class TestShape:
    @pytest.fixture
    def script(self) -> str:
        return strip_comments(SCHEMA.read_text(encoding='utf-8'))

    @pytest.fixture
    def table_names(self, schema_inspection: sqlite3.Connection) -> list[str]:
        rows = schema_inspection.execute(
            "SELECT name FROM pragma_table_list WHERE schema = 'main' AND type = 'table'"
            " AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [name for (name,) in rows]

    def test_the_table_set_is_the_designed_one(self, table_names: list[str]) -> None:
        assert set(table_names) == TABLES

    def test_every_table_is_strict(self, schema_inspection: sqlite3.Connection) -> None:
        loose = schema_inspection.execute(
            "SELECT name FROM pragma_table_list WHERE schema = 'main' AND type = 'table'"
            " AND name NOT LIKE 'sqlite_%' AND strict = 0"
        ).fetchall()
        assert loose == []

    def test_every_table_has_an_integer_primary_key_named_id(
        self, schema_inspection: sqlite3.Connection, table_names: list[str]
    ) -> None:
        mismatched = [
            name
            for name in table_names
            if schema_inspection.execute(
                'SELECT name, type FROM pragma_table_info(?) WHERE pk > 0', (name,)
            ).fetchall()
            != [('id', 'INTEGER')]
        ]
        assert mismatched == []

    def test_every_foreign_key_column_leads_an_index(
        self, schema_inspection: sqlite3.Connection, table_names: list[str]
    ) -> None:
        unindexed = [
            (name, column)
            for name in table_names
            for (column,) in schema_inspection.execute(
                'SELECT "from" FROM pragma_foreign_key_list(?)', (name,)
            ).fetchall()
            if not schema_inspection.execute(
                'SELECT 1 FROM pragma_index_list(?) AS i'
                ' JOIN pragma_index_info(i.name) AS c ON c.seqno = 0 AND c.name = ?',
                (name, column),
            ).fetchone()
        ]
        assert unindexed == []

    def test_every_index_is_named_with_its_prefix(self, script: str) -> None:
        names = re.findall(r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\w+)', script)
        assert names
        assert [name for name in names if not name.startswith('ix_')] == []

    @pytest.mark.parametrize('keyword', list(CONSTRAINT_PREFIXES))
    def test_every_constraint_is_named_with_its_prefix(self, script: str, keyword: str) -> None:
        prefix = CONSTRAINT_PREFIXES[keyword]
        named = re.findall(rf'CONSTRAINT\s+(\w+)\s+{keyword}\b', script)
        declared = re.findall(rf'\b{keyword}\b', script)
        assert len(named) == len(declared)
        assert [name for name in named if not name.startswith(prefix)] == []

    def test_user_version_matches_the_script(
        self, script: str, schema_inspection: sqlite3.Connection
    ) -> None:
        match = re.search(r'PRAGMA\s+user_version\s*=\s*(\d+)', script)
        assert match is not None
        stored = schema_inspection.execute('PRAGMA user_version').fetchone()
        assert stored == (int(match.group(1)),)

    def test_database_stamped_by_the_old_plugin_is_refused(
        self, database_path: Path, database_spec: DatabaseSpec
    ) -> None:
        with closing(sqlite3.connect(database_path)) as old_plugin:
            old_plugin.execute('PRAGMA user_version = 1')
        with pytest.raises(SchemaVersionError) as refused:
            open_database(database_path, database_spec, ConnectionOptions())
        assert refused.value.found == 1
