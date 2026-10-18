from importlib.resources import files
from typing import TYPE_CHECKING

import msgspec
import pytest
from mightymodels_core.database import parse_blocks
from mightymodels_core.schemas import DECLARATIONS

if TYPE_CHECKING:
    import sqlite3

    from mightymodels_core.database import Declaration

pytestmark = pytest.mark.integration

BLOCKS = parse_blocks(
    files('mightymodels_core.sql').joinpath('statements.sql').read_text(encoding='utf-8')
)
EXEMPT_SCAN_TARGETS = ('json_each', 'json_tree', '(subquery', 'subquery')


def is_base_table_scan(detail: str) -> bool:
    if not detail.startswith('SCAN '):
        return False

    target = detail.removeprefix('SCAN ')
    return not (target.startswith(EXEMPT_SCAN_TARGETS) or 'VIRTUAL TABLE INDEX' in target)


def unbound_fields(declaration: Declaration) -> dict[str, None]:
    return dict.fromkeys(field.name for field in msgspec.structs.fields(declaration.params))


@pytest.mark.parametrize('declaration', DECLARATIONS, ids=lambda declaration: declaration.name)
def test_declared_statement_is_served_by_an_index(
    plan_connection: sqlite3.Connection, declaration: Declaration
) -> None:
    plan = plan_connection.execute(
        f'EXPLAIN QUERY PLAN {BLOCKS[declaration.name]}', unbound_fields(declaration)
    ).fetchall()

    scans = [row[3] for row in plan if is_base_table_scan(row[3])]

    assert scans == []


def test_every_block_has_a_declaration() -> None:
    assert set(BLOCKS) == {declaration.name for declaration in DECLARATIONS}
