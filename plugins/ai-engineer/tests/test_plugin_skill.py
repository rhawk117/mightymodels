import re
from pathlib import Path

from ai_engineer_cli.plugin.kinds import KIND_SPECS

SKILLS = Path(__file__).resolve().parents[1] / 'skills'
PLAN_PLUGIN = SKILLS / 'plan-plugin'
KIND_ROW = re.compile(
    r'^\| (?P<kind>[a-z-]+) +\| (?P<builder>[`a-z-]+) +\| .*\| `(?P<reference>[^`]+)` +\|$'
)
NO_BUILDER = 'manual'


def kind_table() -> dict[str, tuple[str | None, str]]:
    """The kind, builder and reference of each row of the SKILL.md kind table."""
    rows = (KIND_ROW.match(line) for line in (PLAN_PLUGIN / 'SKILL.md').read_text().splitlines())
    table = {}
    for row in filter(None, rows):
        builder = row['builder'].strip('`')
        table[row['kind']] = (None if builder == NO_BUILDER else builder, row['reference'])
    return table


def test_every_builder_in_the_kind_specs_is_a_skill_directory() -> None:
    builders = {spec.builder for spec in KIND_SPECS.values() if spec.builder}

    assert builders
    for builder in builders:
        assert (SKILLS / builder / 'SKILL.md').is_file()


def test_kind_table_lists_the_kinds_and_builders_of_the_kind_specs() -> None:
    expected = {kind: spec.builder for kind, spec in KIND_SPECS.items()}

    assert {kind: builder for kind, (builder, _) in kind_table().items()} == expected


def test_kind_table_names_each_reference_file_the_render_writes_into_plan_md() -> None:
    expected = {kind: spec.reference for kind, spec in KIND_SPECS.items() if spec.reference}
    listed = {kind: reference for kind, (_, reference) in kind_table().items()}

    assert {kind: listed[kind] for kind in expected} == expected
    for reference in listed.values():
        assert (PLAN_PLUGIN / reference).is_file()


def test_every_reference_file_is_named_in_the_skill_body() -> None:
    body = (PLAN_PLUGIN / 'SKILL.md').read_text()

    for reference in (PLAN_PLUGIN / 'references').glob('*.md'):
        assert f'references/{reference.name}' in body
