import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import msgspec
from hypothesis import given
from hypothesis import strategies as st
from mightymodels_core.database import ConnectionOptions, open_database
from mightymodels_core.schemas import DECLARATIONS

if TYPE_CHECKING:
    import pytest
    from mightymodels_core.database import DatabaseSpec, Declaration

EXEMPT_SCAN_TARGETS = ('json_each', 'json_tree', '(subquery', 'subquery')


def is_base_table_scan(detail: str) -> bool:
    if not detail.startswith('SCAN '):
        return False

    target = detail.removeprefix('SCAN ')
    return not (target.startswith(EXEMPT_SCAN_TARGETS) or 'VIRTUAL TABLE INDEX' in target)


def unbound_fields(declaration: Declaration) -> dict[str, None]:
    return dict.fromkeys(field.name for field in msgspec.structs.fields(declaration.params))


class TestCataloguePlans:
    declarations = st.sampled_from(DECLARATIONS)

    def find_scans(
        self,
        tmp_path_factory: pytest.TempPathFactory,
        database_spec: DatabaseSpec,
        blocks: dict[str, str],
        declaration: Declaration,
    ) -> list[str]:
        path = tmp_path_factory.mktemp('plan').joinpath('mightymodels.db')
        open_database(path, database_spec, ConnectionOptions()).close()
        with closing(sqlite3.connect(path)) as connection:
            plan = connection.execute(
                f'EXPLAIN QUERY PLAN {blocks[declaration.name]}', unbound_fields(declaration)
            ).fetchall()
        return [row[3] for row in plan if is_base_table_scan(row[3])]

    @given(declaration=declarations)
    def test_declared_statement_is_served_by_an_index(
        self,
        tmp_path_factory: pytest.TempPathFactory,
        database_spec: DatabaseSpec,
        blocks: dict[str, str],
        declaration: Declaration,
    ) -> None:
        scans = self.find_scans(tmp_path_factory, database_spec, blocks, declaration)

        assert scans == []
