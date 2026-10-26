from dataclasses import dataclass
from pathlib import Path

import pytest
from mightymodels_mcp.server.entrypoint import create_catalog

HEADING = '## Tool map'
HINT_NAMES = ('read_only_hint', 'destructive_hint', 'idempotent_hint', 'open_world_hint')


@dataclass(slots=True, kw_only=True, frozen=True)
class DocRow:
    old_tool: str
    old_action: str
    new_tool: str
    input_fields: str
    title: str
    hints: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class RegisteredTool:
    name: str
    input_fields: str
    title: str
    hints: tuple[str, ...]


def parse_row(line: str) -> DocRow:
    cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
    old_tool, old_action, new_tool, input_fields, title, *hints = cells
    return DocRow(
        old_tool=old_tool.strip('`'),
        old_action=old_action.strip('`'),
        new_tool=new_tool.strip('`'),
        input_fields=input_fields,
        title=title,
        hints=tuple(hints),
    )


def read_rows(text: str) -> list[DocRow]:
    section = text.split(HEADING, 1)[1].split('\n## ', 1)[0]
    table = [line for line in section.splitlines() if line.startswith('|')]
    return [parse_row(line) for line in table[2:]]


def register(name: str) -> RegisteredTool:
    tool = create_catalog().tools[name]
    properties = tool.parameters.get('properties', {})
    return RegisteredTool(
        name=name,
        input_fields=', '.join(f'`{field}`' for field in properties) or 'none',
        title=tool.title or '',
        hints=tuple(str(getattr(tool.annotations, hint)).lower() for hint in HINT_NAMES),
    )


class TestMappingDoc:
    document = Path(__file__).resolve().parents[4] / 'docs' / 'workflow-state-tools.md'
    row_count = 32

    @pytest.fixture
    def rows(self) -> list[DocRow]:
        return read_rows(self.document.read_text(encoding='utf-8'))

    @pytest.fixture
    def registered(self) -> dict[str, RegisteredTool]:
        return {name: register(name) for name in create_catalog().tools}

    def test_table_has_one_row_per_tool(self, rows: list[DocRow]) -> None:
        assert len(rows) == self.row_count

    def test_new_names_equal_registered_names(
        self, rows: list[DocRow], registered: dict[str, RegisteredTool]
    ) -> None:
        assert sorted(row.new_tool for row in rows) == sorted(registered)

    def test_old_pairs_are_unique(self, rows: list[DocRow]) -> None:
        pairs = [(row.old_tool, row.old_action) for row in rows]
        assert len(set(pairs)) == len(pairs)

    def test_each_row_matches_its_registered_tool(
        self, rows: list[DocRow], registered: dict[str, RegisteredTool]
    ) -> None:
        documented = {
            row.new_tool: RegisteredTool(
                name=row.new_tool,
                input_fields=row.input_fields,
                title=row.title,
                hints=row.hints,
            )
            for row in rows
        }
        assert documented == registered
