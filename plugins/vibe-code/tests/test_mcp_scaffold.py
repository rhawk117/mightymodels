import ast
import json
import re
import shutil
import tomllib
from pathlib import Path

import pytest
from vibe_code_cli.builtin import Services
from vibe_code_cli.cli import main
from vibe_code_cli.findings import CannotCheckError
from vibe_code_cli.mcp.scaffold import command
from vibe_code_cli.mcp.scaffold.render import plan_project, write_project
from vibe_code_cli.mcp.scaffold.spec import load_spec
from vibe_code_cli.mcp.tests.support import (
    EXAMPLE_SPEC,
    TEMPLATE,
    McpScaffold,
    ServicesFactory,
    example_spec,
    rendered_args,
    rendered_config,
    scaffold,
    tool_changes,
    written_text,
)


class TestUsage:
    def test_scaffold_help_shows_spec_target_and_options(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['mcp', 'scaffold', '--help'])

        assert exit_info.value.code == 0
        output = capsys.readouterr().out
        for text in ('SPEC', 'TARGET', '--template', '--force'):
            assert text in output


class TestExampleSpec:
    TOKEN = re.compile(r'__[A-Z][A-Z_]*__')
    CONFIGS = (
        ('mcp.plugin.json', 'plugin'),
        ('mcp.project.json', 'project'),
        ('mcp.network.json', 'project'),
    )

    @pytest.fixture
    def no_findings(self, fake_services: ServicesFactory) -> Services:
        return fake_services(())

    def test_example_spec_scaffolds_parsable_python_and_valid_configs(
        self, mcp_scaffold: McpScaffold, no_findings: Services
    ) -> None:
        target = mcp_scaffold.target

        assert scaffold(EXAMPLE_SPEC, target, '--template', str(TEMPLATE)) == 0

        python_files = sorted(target.rglob('*.py'))
        assert len(python_files) > 10
        for path in python_files:
            ast.parse(path.read_text(), filename=str(path))
        assert self.TOKEN.findall(written_text(target)) == []
        for name, kind in self.CONFIGS:
            config = target / 'config' / name
            argv = ['mcp', 'validate', str(config), '--kind', kind]
            assert main(argv, no_findings) == 0


class TestDefaultTemplate:
    @pytest.fixture
    def exported_plugin_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('VIBE_CODE_PLUGIN_ROOT', str(tmp_path / 'plugin'))
        template = tmp_path / 'plugin' / 'skills' / 'create-mcp' / 'assets' / 'template'
        template.mkdir(parents=True)
        (template / 'NOTE.md').write_text('# __NAME__\n')

    @pytest.fixture
    def no_export(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('VIBE_CODE_PLUGIN_ROOT', raising=False)

    @pytest.mark.usefixtures('exported_plugin_root')
    def test_default_template_comes_from_the_exported_plugin_root(
        self, mcp_scaffold: McpScaffold
    ) -> None:
        target = mcp_scaffold.target

        assert scaffold(EXAMPLE_SPEC, target) == 0
        assert (target / 'NOTE.md').read_text() == '# repo-inspector\n'

    @pytest.mark.usefixtures('no_export')
    def test_default_template_without_the_export_is_the_skills_template(self) -> None:
        assert command.default_template() == TEMPLATE


class TestRenderedConfigs:
    @pytest.fixture
    def always_load_on(self, mcp_scaffold: McpScaffold) -> Path:
        directory = mcp_scaffold.root / 'on'
        directory.mkdir()
        spec = mcp_scaffold.write_spec(example_spec(always_load=True), directory)
        assert scaffold(spec, directory / 'out') == 0
        return directory / 'out'

    @pytest.fixture
    def always_load_off(self, mcp_scaffold: McpScaffold) -> Path:
        directory = mcp_scaffold.root / 'off'
        directory.mkdir()
        assert scaffold(mcp_scaffold.write_spec(example_spec(), directory), directory / 'out') == 0
        return directory / 'out'

    def test_mc_a28_rendered_configs_are_the_three_mcp_json_shapes(
        self, mcp_scaffold: McpScaffold
    ) -> None:
        target = mcp_scaffold.scaffolded()
        name = 'repo-inspector'

        assert rendered_config(target, 'mcp.plugin.json') == {
            name: {
                'command': 'uv',
                'args': ['run', '--project', f'${{CLAUDE_PLUGIN_ROOT}}/mcp/{name}', name],
            }
        }
        assert rendered_config(target, 'mcp.project.json') == {
            name: {
                'type': 'stdio',
                'command': 'uv',
                'args': ['run', '--project', f'mcp/{name}', name],
                'timeout': 120000,
            }
        }
        assert rendered_config(target, 'mcp.network.json') == {
            name: {'type': 'http', 'url': 'http://127.0.0.1:8000/mcp'}
        }

    @pytest.mark.parametrize(
        ('reach', 'files'),
        [
            pytest.param('local', ['mcp.plugin.json', 'mcp.project.json'], id='local-files0'),
            pytest.param('network', ['mcp.network.json'], id='network-files1'),
        ],
    )
    def test_reach_picks_the_config_files(
        self, mcp_scaffold: McpScaffold, reach: str, files: list[str]
    ) -> None:
        target = mcp_scaffold.scaffolded(reach=reach)

        assert sorted(path.name for path in (target / 'config').iterdir()) == files

    def test_mc_a6_a16_network_snippet_is_http_with_a_url(self, mcp_scaffold: McpScaffold) -> None:
        target = mcp_scaffold.scaffolded(reach='network')

        entry = rendered_config(target, 'mcp.network.json')['repo-inspector']
        assert entry['type'] == 'http'
        assert entry['url'] == 'http://127.0.0.1:8000/mcp'

    def test_mc_a7_no_config_carries_a_tools_key(self, mcp_scaffold: McpScaffold) -> None:
        target = mcp_scaffold.scaffolded()

        for path in (target / 'config').iterdir():
            assert 'tools' not in json.loads(path.read_text())['mcpServers']['repo-inspector']

    def test_mc_a8_a11_project_timeout_and_plugin_root_variable(
        self, mcp_scaffold: McpScaffold
    ) -> None:
        target = mcp_scaffold.scaffolded()

        assert rendered_config(target, 'mcp.project.json')['repo-inspector']['timeout'] == 120000
        plugin_args = rendered_args(target, 'mcp.plugin.json', 'repo-inspector')
        assert '${CLAUDE_PLUGIN_ROOT}/mcp/repo-inspector' in plugin_args

    def test_mc_b6_always_load_renders_always_load_true_in_every_shape(
        self, always_load_on: Path, always_load_off: Path
    ) -> None:
        for name in ('mcp.plugin.json', 'mcp.project.json', 'mcp.network.json'):
            assert rendered_config(always_load_on, name)['repo-inspector']['alwaysLoad'] is True
            assert 'alwaysLoad' not in rendered_config(always_load_off, name)['repo-inspector']


class TestRootSource:
    def test_mc_a12_a13_env_root_source_reads_claude_project_dir(
        self, mcp_scaffold: McpScaffold
    ) -> None:
        target = mcp_scaffold.scaffolded(root_source='env')

        cli = (target / 'src' / 'repo_inspector' / 'cli.py').read_text()
        assert "ROOT_VARIABLE: str | None = 'CLAUDE_PROJECT_DIR'" in cli
        spec = json.loads((target / 'mcp-spec.json').read_text())
        assert all(item['name'] != 'root' for tool in spec['tools'] for item in tool['inputs'])

    def test_parameter_root_source_adds_a_root_input_to_every_tool(
        self, mcp_scaffold: McpScaffold
    ) -> None:
        target = mcp_scaffold.scaffolded(root_source='parameter')

        spec = json.loads((target / 'mcp-spec.json').read_text())
        assert all(tool['inputs'][0]['name'] == 'root' for tool in spec['tools'])
        server = (target / 'src' / 'repo_inspector' / 'server.py').read_text()
        assert 'workspace_of(ctx, params.root)' in server

    def test_cwd_root_source_has_no_environment_variable(self, mcp_scaffold: McpScaffold) -> None:
        target = mcp_scaffold.scaffolded()

        cli = (target / 'src' / 'repo_inspector' / 'cli.py').read_text()
        assert 'ROOT_VARIABLE: str | None = None' in cli

    def test_mc_b5_roots_root_source_asks_the_client_for_roots_list(
        self, mcp_scaffold: McpScaffold
    ) -> None:
        target = mcp_scaffold.scaffolded(root_source='roots')

        package = target / 'src' / 'repo_inspector'
        assert 'session.list_roots()' in (package / 'workspace.py').read_text()
        server = (package / 'server.py').read_text()
        assert 'await listed_root(ctx.request_context.session)' in server
        assert 'import asyncio' in server
        assert 'async def list_changed_files(' in server
        assert 'ROOT_VARIABLE: str | None = ' in (package / 'cli.py').read_text()
        for path in package.rglob('*.py'):
            ast.parse(path.read_text())


class TestToolMeta:
    def test_mc_b7_destructive_tools_force_a_permission_prompt(
        self, mcp_scaffold: McpScaffold
    ) -> None:
        server = (mcp_scaffold.scaffolded() / 'src' / 'repo_inspector' / 'server.py').read_text()

        destructive = server.split("name='clean_untracked'")[1]
        assert "meta={'anthropic/requiresUserInteraction': True}" in destructive
        assert server.count('anthropic/requiresUserInteraction') == 1

    def test_mc_b8_max_result_chars_becomes_tool_meta(self, mcp_scaffold: McpScaffold) -> None:
        server = (mcp_scaffold.scaffolded() / 'src' / 'repo_inspector' / 'server.py').read_text()

        assert "meta={'anthropic/maxResultSizeChars': 100000}" in server
        assert server.count('anthropic/maxResultSizeChars') == 1

    def test_max_result_chars_over_the_ceiling_is_rejected(
        self, mcp_scaffold: McpScaffold, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec = mcp_scaffold.write_spec(example_spec(**tool_changes(max_result_chars=500001)))

        assert scaffold(spec, mcp_scaffold.target) == 2
        assert 'max_result_chars' in capsys.readouterr().err


class TestInstructionsLength:
    def test_mc_a19_long_instructions_warn_without_echoing_them(
        self, mcp_scaffold: McpScaffold, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec = mcp_scaffold.write_spec(example_spec(instructions='x' * 2049))

        assert scaffold(spec, mcp_scaffold.target) == 0
        captured = capsys.readouterr()
        assert 'warning: instructions is 2049 characters' in captured.err
        assert 'xxxxxxxx' not in captured.err + captured.out

    def test_mc_a19_instructions_at_the_limit_do_not_warn(
        self, mcp_scaffold: McpScaffold, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec = mcp_scaffold.write_spec(example_spec(instructions='x' * 2048))

        assert scaffold(spec, mcp_scaffold.target) == 0
        assert 'warning' not in capsys.readouterr().err


class TestRejectedSpec:
    CANARY = 'sk-live-0123456789'

    @pytest.mark.parametrize(
        'name',
        [
            pytest.param('a' * 65, id='a' * 65),
            pytest.param('bad name', id='bad name'),
            pytest.param('bad-name', id='bad-name'),
            pytest.param('', id=''),
        ],
    )
    def test_mc_a20_input_name_that_breaks_the_property_rule_is_rejected(
        self, mcp_scaffold: McpScaffold, name: str
    ) -> None:
        inputs = [{'name': name, 'type': 'str'}]
        spec = mcp_scaffold.write_spec(example_spec(**tool_changes(1, inputs=inputs)))

        assert scaffold(spec, mcp_scaffold.target) == 2
        assert not mcp_scaffold.target.exists()

    @pytest.mark.parametrize(
        ('changes', 'tool'),
        [
            pytest.param({'name': '../x'}, {}, id='changes0'),
            pytest.param({'name': '/etc/x'}, {}, id='changes1'),
            pytest.param({'name': 'Bad_Name'}, {}, id='changes2'),
            pytest.param({'name': 'trailing\n'}, {}, id='changes3'),
            pytest.param({'package': '../x'}, {}, id='changes4'),
            pytest.param({'package': '/etc/x'}, {}, id='changes5'),
            pytest.param({'package': 'class'}, {}, id='changes6'),
            pytest.param({}, {'name': '../x'}, id='changes7'),
            pytest.param({}, {'name': '/etc/x'}, id='changes8'),
            pytest.param({'resources': [{'uri': 'repo://{a}', 'name': '../x'}]}, {}, id='changes9'),
            pytest.param(
                {'prompts': [{'name': 'ok', 'template': '{__import__}'}]}, {}, id='changes10'
            ),
        ],
    )
    def test_names_that_become_paths_or_code_are_rejected_before_any_write(
        self, mcp_scaffold: McpScaffold, changes: dict[str, object], tool: dict[str, object]
    ) -> None:
        spec = mcp_scaffold.write_spec(example_spec(**changes, **tool_changes(0, **tool)))

        assert scaffold(spec, mcp_scaffold.target) == 2
        assert not mcp_scaffold.target.exists()

    def test_spec_values_are_not_printed_by_a_rejection_or_a_success(
        self, mcp_scaffold: McpScaffold, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad = mcp_scaffold.write_spec(example_spec(description=self.CANARY, package=self.CANARY))
        assert scaffold(bad, mcp_scaffold.root / 'bad') == 2
        good = mcp_scaffold.write_spec(example_spec(description=self.CANARY))
        assert scaffold(good, mcp_scaffold.root / 'good') == 0

        captured = capsys.readouterr()
        assert self.CANARY not in captured.out + captured.err

    @pytest.mark.parametrize(
        ('spec_text', 'reason'),
        [
            pytest.param('{not json', 'not valid JSON', id='{not json-not valid JSON'),
            pytest.param(
                '[]', 'Expected `object`, got `array`', id='[]-Expected `object`, got `array`'
            ),
            pytest.param('{"name": "a"}', 'tool', id='{"name": "a"}-tool'),
        ],
    )
    def test_spec_it_rejects_exits_two_with_a_reason(
        self,
        mcp_scaffold: McpScaffold,
        capsys: pytest.CaptureFixture[str],
        spec_text: str,
        reason: str,
    ) -> None:
        spec = mcp_scaffold.write_spec_text(spec_text)

        assert scaffold(spec, mcp_scaffold.target) == 2
        assert reason in capsys.readouterr().err

    @pytest.mark.parametrize(
        ('spec_text', 'reason'),
        [
            pytest.param(
                '{"name": 7}',
                'Expected `str`, got `int` - at `$.name`',
                id='{"name": 7}-Expected `str`, got `int` - at `$.name`',
            ),
            pytest.param(
                '{"name": "a", "tools": {}}',
                'Expected `array`, got `object` - at `$.tools`',
                id='{"name": "a", "tools": {}}-Expected `array`, got `object` - at `$.tools`',
            ),
            pytest.param(
                '{"name": "a", "tools": [{"confirm": "yes"}]}',
                'at `$.tools[0].confirm`',
                id='{"name": "a", "tools": [{"confirm": "yes"}]}-at `$.tools[0].confirm`',
            ),
            pytest.param(
                '{"name": "a", "tools": [{"max_result_chars": 0}]}',
                'at `$.tools[0].max_result_chars`',
                id=(
                    '{"name": "a", "tools": [{"max_result_chars": 0}]}'
                    '-at `$.tools[0].max_result_chars`'
                ),
            ),
        ],
    )
    def test_a_value_of_the_wrong_type_prints_the_decoder_message_and_writes_nothing(
        self,
        mcp_scaffold: McpScaffold,
        capsys: pytest.CaptureFixture[str],
        spec_text: str,
        reason: str,
    ) -> None:
        spec = mcp_scaffold.write_spec_text(spec_text)

        assert scaffold(spec, mcp_scaffold.target) == 2
        assert reason in capsys.readouterr().err
        assert not mcp_scaffold.target.exists()

    @pytest.mark.parametrize(
        'text',
        [
            pytest.param('has a \\u007f in it', id='has a \\u007f in it'),
            pytest.param('has a \\u0001 in it', id='has a \\u0001 in it'),
            pytest.param('has a \\u000b in it', id='has a \\u000b in it'),
            pytest.param('has a \\ud800 in it', id='has a \\ud800 in it'),
        ],
    )
    def test_control_characters_and_lone_surrogates_in_spec_text_are_rejected_before_any_write(
        self, mcp_scaffold: McpScaffold, capsys: pytest.CaptureFixture[str], text: str
    ) -> None:
        document = json.dumps(example_spec(description='x')).replace('"x"', f'"{text}"')
        spec = mcp_scaffold.write_spec_text(document)

        assert scaffold(spec, mcp_scaffold.target) == 2
        assert 'has a' not in capsys.readouterr().err
        assert not mcp_scaffold.target.exists()

    def test_tab_newline_and_carriage_return_are_allowed_in_spec_text(
        self, mcp_scaffold: McpScaffold
    ) -> None:
        spec = mcp_scaffold.write_spec(example_spec(description='one\ttwo\nthree\r\nfour'))

        assert scaffold(spec, mcp_scaffold.target) == 0

    def test_missing_spec_exits_two(
        self, mcp_scaffold: McpScaffold, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert scaffold(mcp_scaffold.root / 'absent.json', mcp_scaffold.target) == 2
        assert 'cannot read the spec' in capsys.readouterr().err


class TestTarget:
    @pytest.fixture
    def escaping_plan(self) -> dict[str, str]:
        return {'ok.txt': 'fine', '../escape.txt': 'bad'}

    @pytest.fixture
    def outside(self, mcp_scaffold: McpScaffold) -> Path:
        directory = mcp_scaffold.root / 'outside'
        directory.mkdir()
        return directory

    @pytest.fixture
    def symlinked_target(self, mcp_scaffold: McpScaffold, outside: Path) -> Path:
        mcp_scaffold.target.mkdir()
        (mcp_scaffold.target / 'config').symlink_to(outside, target_is_directory=True)
        return mcp_scaffold.target

    @pytest.fixture
    def occupied_target(self, mcp_scaffold: McpScaffold) -> Path:
        mcp_scaffold.target.mkdir()
        (mcp_scaffold.target / 'keep.txt').write_text('mine')
        return mcp_scaffold.target

    @pytest.fixture
    def stale_tree(self, mcp_scaffold: McpScaffold) -> Path:
        stale = mcp_scaffold.scaffolded() / 'src' / 'repo_inspector' / 'tools' / 'removed_tool'
        stale.mkdir()
        return stale

    def test_plan_that_escapes_the_target_writes_nothing(
        self, mcp_scaffold: McpScaffold, escaping_plan: dict[str, str]
    ) -> None:
        with pytest.raises(CannotCheckError, match='outside'):
            write_project(mcp_scaffold.target, escaping_plan, force=False)
        assert not mcp_scaffold.target.exists()
        assert not (mcp_scaffold.root / 'escape.txt').exists()

    def test_symlink_in_a_forced_target_cannot_redirect_a_write(
        self, symlinked_target: Path, outside: Path
    ) -> None:
        with pytest.raises(CannotCheckError, match='outside'):
            write_project(symlinked_target, {'config/mcp.plugin.json': '{}'}, force=True)
        assert list(outside.iterdir()) == []

    def test_non_empty_target_needs_force(
        self, occupied_target: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert scaffold(EXAMPLE_SPEC, occupied_target) == 2
        assert '--force' in capsys.readouterr().err
        assert list(occupied_target.iterdir()) == [occupied_target / 'keep.txt']
        assert scaffold(EXAMPLE_SPEC, occupied_target, '--force') == 0
        assert (occupied_target / 'keep.txt').read_text() == 'mine'

    def test_force_replaces_a_stale_src_tree(
        self, mcp_scaffold: McpScaffold, stale_tree: Path
    ) -> None:
        assert scaffold(EXAMPLE_SPEC, mcp_scaffold.target, '--force') == 0
        assert not stale_tree.exists()


class TestTemplate:
    @pytest.fixture
    def cached_template(self, mcp_scaffold: McpScaffold) -> Path:
        template = mcp_scaffold.root / 'template'
        shutil.copytree(TEMPLATE, template)
        ruff_cache = template / '.ruff_cache'
        bytecode_cache = template / 'src' / '__PKG__' / '__pycache__'
        (ruff_cache / '0.1').mkdir(parents=True, exist_ok=True)
        bytecode_cache.mkdir(exist_ok=True)
        (ruff_cache / '0.1' / 'blob').write_bytes(b'\xff\xfe\x00')
        (bytecode_cache / 'server.cpython-314.pyc').write_bytes(b'\xff\xfe\x00')
        (ruff_cache / 'CACHEDIR.TAG').write_text('Signature: 8a477f597d28d172789f06886806bc55\n')
        return template

    def test_missing_template_exits_two(
        self, mcp_scaffold: McpScaffold, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = scaffold(
            EXAMPLE_SPEC, mcp_scaffold.target, '--template', str(mcp_scaffold.root / 'absent')
        )

        assert code == 2
        assert 'is not a directory' in capsys.readouterr().err

    def test_tool_caches_in_the_template_are_left_out_of_the_plan(
        self, cached_template: Path
    ) -> None:
        loaded = load_spec(EXAMPLE_SPEC)

        plan = plan_project(loaded, cached_template)

        assert [path for path in plan if '.ruff_cache' in path or '__pycache__' in path] == []
        assert plan == plan_project(loaded, TEMPLATE)

    def test_template_pyproject_is_valid_toml(self) -> None:
        project = tomllib.loads((TEMPLATE / 'pyproject.toml').read_text())['project']

        assert project['description'] == '__DESCRIPTION_TOML__'


class TestScaffoldedRecord:
    HOSTILE_DESCRIPTION = 'uses __NAME__ and """ with a \\ backslash'
    UNICODE_DESCRIPTION = 'says "hi" with a \\ backslash and \U0001f600'

    def test_the_record_keeps_the_spec_keys_in_order_and_appends_the_defaults(
        self, mcp_scaffold: McpScaffold
    ) -> None:
        target = mcp_scaffold.scaffolded()
        record = json.loads((target / 'mcp-spec.json').read_text())
        written = example_spec()

        assert list(record)[: len(written)] == list(written)
        assert list(record)[len(written) :] == ['package', 'always_load']
        assert record['scope'] == 'project'
        assert list(record['tools'][1])[-3:] == ['binary', 'arguments', 'confirm']

    def test_spec_text_is_substituted_once_and_cannot_break_out_of_a_docstring(
        self, mcp_scaffold: McpScaffold
    ) -> None:
        target = mcp_scaffold.scaffolded(
            description=self.HOSTILE_DESCRIPTION,
            **tool_changes(0, description=self.HOSTILE_DESCRIPTION),
        )

        assert 'uses __NAME__ and' in (target / 'README.md').read_text()
        for path in target.rglob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
        assert 'description = "uses __NAME__' in (target / 'pyproject.toml').read_text()

    def test_description_round_trips_through_the_generated_pyproject(
        self, mcp_scaffold: McpScaffold
    ) -> None:
        target = mcp_scaffold.scaffolded(description=self.UNICODE_DESCRIPTION)

        pyproject = (target / 'pyproject.toml').read_text(encoding='utf-8')
        assert tomllib.loads(pyproject)['project']['description'] == self.UNICODE_DESCRIPTION
