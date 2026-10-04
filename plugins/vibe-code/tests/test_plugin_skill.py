import re

import pytest
from vibe_code_cli.plugin.kinds import Kinds
from vibe_code_cli.plugin.tests.support import PLAN_PLUGIN, SKILLS

type KindTable = dict[str, tuple[str | None, str]]


class TestBuilders:
    def test_every_builder_in_the_kind_specs_is_a_skill_directory(self) -> None:
        builders = {spec.builder for spec in Kinds().specs.values() if spec.builder}

        assert builders
        for builder in builders:
            assert (SKILLS / builder / 'SKILL.md').is_file()


class TestKindTable:
    KIND_ROW = re.compile(
        r'^\| (?P<kind>[a-z-]+) +\| (?P<builder>[`a-z-]+) +\| .*\| `(?P<reference>[^`]+)` +\|$'
    )
    NO_BUILDER = 'manual'

    @pytest.fixture
    def kind_table(self) -> KindTable:
        lines = (PLAN_PLUGIN / 'SKILL.md').read_text().splitlines()
        table = {}
        for row in filter(None, (self.KIND_ROW.match(line) for line in lines)):
            builder = row['builder'].strip('`')
            table[row['kind']] = (None if builder == self.NO_BUILDER else builder, row['reference'])
        return table

    def test_kind_table_lists_the_kinds_and_builders_of_the_kind_specs(
        self, kind_table: KindTable
    ) -> None:
        expected = {kind: spec.builder for kind, spec in Kinds().specs.items()}

        assert {kind: builder for kind, (builder, _) in kind_table.items()} == expected

    def test_kind_table_names_each_reference_file_the_render_writes_into_plan_md(
        self, kind_table: KindTable
    ) -> None:
        expected = {kind: spec.reference for kind, spec in Kinds().specs.items() if spec.reference}
        listed = {kind: reference for kind, (_, reference) in kind_table.items()}

        assert {kind: listed[kind] for kind in expected} == expected
        for reference in listed.values():
            assert (PLAN_PLUGIN / reference).is_file()


class TestSkillBody:
    def test_every_reference_file_is_named_in_the_skill_body(self) -> None:
        body = (PLAN_PLUGIN / 'SKILL.md').read_text()

        for reference in (PLAN_PLUGIN / 'references').glob('*.md'):
            assert f'references/{reference.name}' in body
