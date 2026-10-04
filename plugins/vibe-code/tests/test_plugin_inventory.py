import json
from pathlib import Path

import pytest
from vibe_code_cli.cli import main
from vibe_code_cli.plugin.tests.support import (
    PLUGIN_ROOT,
    PluginFiles,
    base_manifest,
    components_of,
    inventory,
    markdown,
)


class TestUsage:
    def test_inventory_help_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['plugin', 'inventory', '--help'])

        assert exit_info.value.code == 0
        assert '--out' in capsys.readouterr().out


class TestBuiltPlugin:
    ONE_PER_FILE = frozenset(
        {
            ('skill', 'add-route'),
            ('agent', 'test-runner'),
            ('agent', 'plain'),
            ('command', 'ship-it'),
            ('hook', 'hooks'),
            ('mcp', 'db'),
            ('lsp', 'pyright'),
            ('executable', 'lint-all'),
            ('output-style', 'terse'),
        }
    )

    def test_pp_a39_inventory_records_one_built_component_per_file(
        self, plugin_built: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert inventory(plugin_built) == 0

        found = components_of(capsys)
        assert set(found) == self.ONE_PER_FILE
        assert {component['status'] for component in found.values()} == {'built'}
        assert found[('agent', 'test-runner')]['files'] == ['agents/sub/runner.md']
        assert found[('skill', 'add-route')]['purpose'] == 'Add a route.'
        assert found[('lsp', 'pyright')]['purpose'] == 'language server for .py'
        assert found[('hook', 'hooks')]['purpose'] == 'hooks with events: PreToolUse, Stop'

    def test_pp_a39_inventory_reads_the_manifest_identity(
        self, plugin_built: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert inventory(plugin_built) == 0

        record = json.loads(capsys.readouterr().out)
        manifest = base_manifest()
        assert record['name'] == manifest['name']
        assert record['version'] == manifest['version']
        assert record['license'] == manifest['license']
        assert record['author'] == manifest['author']


class TestManifestPaths:
    @pytest.fixture
    def plugin_with_skills_override(self, plugin_files: PluginFiles) -> Path:
        plugin_files.write('built-plugin/extra/moved/SKILL.md', markdown('Moved skill.'))
        manifest = {**base_manifest(), 'skills': ['./extra']}
        plugin_files.write('built-plugin/.claude-plugin/plugin.json', json.dumps(manifest))
        return plugin_files.base / 'built-plugin'

    @pytest.fixture
    def plugin_with_inline_servers_and_hooks(self, plugin_files: PluginFiles) -> Path:
        manifest = {
            **base_manifest(),
            'mcpServers': {'search': {'type': 'http', 'url': 'https://example.com/mcp'}},
            'hooks': {'hooks': {'SessionStart': []}},
        }
        plugin_files.write('built-plugin/.claude-plugin/plugin.json', json.dumps(manifest))
        return plugin_files.base / 'built-plugin'

    @pytest.fixture
    def plugin_with_path_leaving_it(self, plugin_files: PluginFiles) -> Path:
        plugin_files.write('outside/stolen/SKILL.md', markdown('Not part of the plugin.'))
        manifest = {**base_manifest(), 'skills': ['../outside']}
        plugin_files.write('built-plugin/.claude-plugin/plugin.json', json.dumps(manifest))
        return plugin_files.base / 'built-plugin'

    def test_pp_a39_inventory_follows_a_manifest_skills_override(
        self, plugin_with_skills_override: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert inventory(plugin_with_skills_override) == 0

        found = components_of(capsys)
        assert found[('skill', 'moved')]['files'] == ['extra/moved/SKILL.md']

    def test_pp_a39_inventory_reads_inline_manifest_servers_and_hooks(
        self, plugin_with_inline_servers_and_hooks: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert inventory(plugin_with_inline_servers_and_hooks) == 0

        found = components_of(capsys)
        assert found[('mcp', 'search')]['purpose'] == 'http server: https://example.com/mcp'
        assert found[('hook', 'hooks')]['files'] == ['.claude-plugin/plugin.json']

    def test_pp_a39_inventory_ignores_a_manifest_path_that_leaves_the_plugin(
        self, plugin_with_path_leaving_it: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert inventory(plugin_with_path_leaving_it) == 0

        assert components_of(capsys) == {}


class TestRecordOutput:
    @pytest.fixture
    def bare_plugin(self, plugin_files: PluginFiles) -> Path:
        plugin_files.write('bare/skills/only/SKILL.md', markdown('Only.'))
        return plugin_files.base / 'bare'

    def test_inventory_out_writes_a_record_that_plugin_validate_accepts(
        self, plugin_built: Path, plugin_files: PluginFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        record = plugin_files.base / 'record.json'

        assert inventory(plugin_built, '--out', str(record)) == 0

        assert f'wrote {record}' in capsys.readouterr().out
        assert main(['plugin', 'validate', str(record)]) == 0

    def test_inventory_of_a_plugin_without_a_manifest_names_the_record_for_the_directory(
        self, bare_plugin: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert inventory(bare_plugin) == 0

        assert json.loads(capsys.readouterr().out)['name'] == 'bare'


class TestUnreadablePlugin:
    NOT_JSON = '{not json'

    @pytest.fixture
    def plugin_with_broken_manifest(self, plugin_files: PluginFiles) -> Path:
        plugin_files.write('broken/.claude-plugin/plugin.json', self.NOT_JSON)
        return plugin_files.base / 'broken'

    def test_inventory_of_a_missing_directory_exits_two(
        self, plugin_files: PluginFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert inventory(plugin_files.base / 'missing') == 2
        assert 'is not a directory' in capsys.readouterr().err

    def test_inventory_of_a_broken_manifest_exits_two(
        self, plugin_with_broken_manifest: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert inventory(plugin_with_broken_manifest) == 2
        assert 'could not inventory' in capsys.readouterr().err


class TestThisPlugin:
    def test_inventory_of_this_plugin_lists_its_skills_and_executable(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert inventory(PLUGIN_ROOT) == 0

        found = components_of(capsys)
        skills = {name for kind, name in found if kind == 'skill'}
        expected = {path.parent.name for path in (PLUGIN_ROOT / 'skills').glob('*/SKILL.md')}
        assert skills == expected
        assert ('executable', 'vibe-code') in found
