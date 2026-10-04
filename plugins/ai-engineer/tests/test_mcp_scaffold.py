import ast
import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
from ai_engineer_cli.cli import main
from ai_engineer_cli.findings import CannotCheckError
from ai_engineer_cli.mcp import command as mcp_group
from ai_engineer_cli.mcp.scaffold import command
from ai_engineer_cli.mcp.scaffold.render import write_project

ASSETS = Path(__file__).resolve().parents[1] / 'skills' / 'create-mcp' / 'assets'
EXAMPLE_SPEC = ASSETS / 'spec.example.json'
TEMPLATE = ASSETS / 'template'
TOKEN = re.compile(r'__[A-Z][A-Z_]*__')
CANARY = 'sk-live-0123456789'


def example_spec(**changes: object) -> dict[str, Any]:
    return {**json.loads(EXAMPLE_SPEC.read_text()), **changes}


def write_spec(directory: Path, spec: dict[str, Any]) -> Path:
    path = directory / 'spec.json'
    path.write_text(json.dumps(spec))
    return path


def scaffold(spec: Path, target: Path, *options: str) -> int:
    return main(['mcp', 'scaffold', str(spec), str(target), *options])


def scaffolded(tmp_path: Path, **changes: object) -> Path:
    target = tmp_path / 'out'
    assert scaffold(write_spec(tmp_path, example_spec(**changes)), target) == 0
    return target


def tool_changes(index: int = 0, **changes: object) -> dict[str, Any]:
    tools = example_spec()['tools']
    tools[index] = {**tools[index], **changes}
    return {'tools': tools}


def rendered_config(target: Path, name: str) -> dict[str, dict[str, Any]]:
    return json.loads((target / 'config' / name).read_text())['mcpServers']


def written_text(target: Path) -> str:
    return '\n'.join(path.read_text() for path in sorted(target.rglob('*')) if path.is_file())


def test_scaffold_help_shows_spec_target_and_options(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['mcp', 'scaffold', '--help'])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    for text in ('SPEC', 'TARGET', '--template', '--force'):
        assert text in output


def test_example_spec_scaffolds_parsable_python_and_valid_configs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mcp_group, 'run_builtin', lambda _target, **_options: [])
    target = tmp_path / 'out'

    assert scaffold(EXAMPLE_SPEC, target, '--template', str(TEMPLATE)) == 0

    python_files = sorted(target.rglob('*.py'))
    assert len(python_files) > 10
    for path in python_files:
        ast.parse(path.read_text(), filename=str(path))
    assert TOKEN.findall(written_text(target)) == []
    for name, kind in [
        ('mcp.plugin.json', 'plugin'),
        ('mcp.project.json', 'project'),
        ('mcp.network.json', 'project'),
    ]:
        config = target / 'config' / name
        assert main(['mcp', 'validate', str(config), '--kind', kind]) == 0


def test_default_template_comes_from_the_exported_plugin_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('AI_ENGINEER_PLUGIN_ROOT', str(tmp_path / 'plugin'))
    template = tmp_path / 'plugin' / 'skills' / 'create-mcp' / 'assets' / 'template'
    template.mkdir(parents=True)
    (template / 'NOTE.md').write_text('# __NAME__\n')
    target = tmp_path / 'out'

    assert scaffold(EXAMPLE_SPEC, target) == 0
    assert (target / 'NOTE.md').read_text() == '# repo-inspector\n'


def test_default_template_without_the_export_is_the_skills_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('AI_ENGINEER_PLUGIN_ROOT', raising=False)

    assert command.default_template() == TEMPLATE


def test_mc_a28_rendered_configs_are_the_three_mcp_json_shapes(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)
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
        ('local', ['mcp.plugin.json', 'mcp.project.json']),
        ('network', ['mcp.network.json']),
    ],
)
def test_reach_picks_the_config_files(tmp_path: Path, reach: str, files: list[str]) -> None:
    target = scaffolded(tmp_path, reach=reach)

    assert sorted(path.name for path in (target / 'config').iterdir()) == files


def test_mc_a6_a16_network_snippet_is_http_with_a_url(tmp_path: Path) -> None:
    entry = rendered_config(scaffolded(tmp_path, reach='network'), 'mcp.network.json')[
        'repo-inspector'
    ]

    assert entry['type'] == 'http'
    assert entry['url'] == 'http://127.0.0.1:8000/mcp'


def test_mc_a7_no_config_carries_a_tools_key(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)

    for path in (target / 'config').iterdir():
        assert 'tools' not in json.loads(path.read_text())['mcpServers']['repo-inspector']


def test_mc_a8_a11_project_timeout_and_plugin_root_variable(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)

    assert rendered_config(target, 'mcp.project.json')['repo-inspector']['timeout'] == 120000
    plugin_args = rendered_config(target, 'mcp.plugin.json')['repo-inspector']['args']
    assert '${CLAUDE_PLUGIN_ROOT}/mcp/repo-inspector' in plugin_args


def test_mc_a12_a13_env_root_source_reads_claude_project_dir(tmp_path: Path) -> None:
    target = scaffolded(tmp_path, root_source='env')

    cli = (target / 'src' / 'repo_inspector' / 'cli.py').read_text()
    assert "ROOT_VARIABLE: str | None = 'CLAUDE_PROJECT_DIR'" in cli
    spec = json.loads((target / 'mcp-spec.json').read_text())
    assert all(item['name'] != 'root' for tool in spec['tools'] for item in tool['inputs'])


def test_parameter_root_source_adds_a_root_input_to_every_tool(tmp_path: Path) -> None:
    target = scaffolded(tmp_path, root_source='parameter')

    spec = json.loads((target / 'mcp-spec.json').read_text())
    assert all(tool['inputs'][0]['name'] == 'root' for tool in spec['tools'])
    server = (target / 'src' / 'repo_inspector' / 'server.py').read_text()
    assert 'workspace_of(ctx, params.root)' in server


def test_cwd_root_source_has_no_environment_variable(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)

    cli = (target / 'src' / 'repo_inspector' / 'cli.py').read_text()
    assert 'ROOT_VARIABLE: str | None = None' in cli


def test_mc_b5_roots_root_source_asks_the_client_for_roots_list(tmp_path: Path) -> None:
    target = scaffolded(tmp_path, root_source='roots')

    package = target / 'src' / 'repo_inspector'
    assert 'session.list_roots()' in (package / 'workspace.py').read_text()
    server = (package / 'server.py').read_text()
    assert 'await listed_root(ctx.request_context.session)' in server
    assert 'import asyncio' in server
    assert 'async def list_changed_files(' in server
    assert 'ROOT_VARIABLE: str | None = ' in (package / 'cli.py').read_text()
    for path in package.rglob('*.py'):
        ast.parse(path.read_text())


def test_mc_b6_always_load_renders_always_load_true_in_every_shape(tmp_path: Path) -> None:
    on = tmp_path / 'on'
    on.mkdir()
    off = tmp_path / 'off'
    off.mkdir()
    for directory, spec in [(on, example_spec(always_load=True)), (off, example_spec())]:
        assert scaffold(write_spec(directory, spec), directory / 'out') == 0

    for name in ('mcp.plugin.json', 'mcp.project.json', 'mcp.network.json'):
        assert rendered_config(on / 'out', name)['repo-inspector']['alwaysLoad'] is True
        assert 'alwaysLoad' not in rendered_config(off / 'out', name)['repo-inspector']


def test_mc_b7_destructive_tools_force_a_permission_prompt(tmp_path: Path) -> None:
    server = (scaffolded(tmp_path) / 'src' / 'repo_inspector' / 'server.py').read_text()

    destructive = server.split("name='clean_untracked'")[1]
    assert "meta={'anthropic/requiresUserInteraction': True}" in destructive
    assert server.count('anthropic/requiresUserInteraction') == 1


def test_mc_b8_max_result_chars_becomes_tool_meta(tmp_path: Path) -> None:
    server = (scaffolded(tmp_path) / 'src' / 'repo_inspector' / 'server.py').read_text()

    assert "meta={'anthropic/maxResultSizeChars': 100000}" in server
    assert server.count('anthropic/maxResultSizeChars') == 1


def test_max_result_chars_over_the_ceiling_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = write_spec(tmp_path, example_spec(**tool_changes(max_result_chars=500001)))

    assert scaffold(spec, tmp_path / 'out') == 2
    assert 'max_result_chars' in capsys.readouterr().err


def test_mc_a19_long_instructions_warn_without_echoing_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = write_spec(tmp_path, example_spec(instructions='x' * 2049))

    assert scaffold(spec, tmp_path / 'out') == 0
    captured = capsys.readouterr()
    assert 'warning: instructions is 2049 characters' in captured.err
    assert 'xxxxxxxx' not in captured.err + captured.out


def test_mc_a19_instructions_at_the_limit_do_not_warn(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = write_spec(tmp_path, example_spec(instructions='x' * 2048))

    assert scaffold(spec, tmp_path / 'out') == 0
    assert 'warning' not in capsys.readouterr().err


@pytest.mark.parametrize('name', ['a' * 65, 'bad name', 'bad-name', ''])
def test_mc_a20_input_name_that_breaks_the_property_rule_is_rejected(
    tmp_path: Path, name: str
) -> None:
    inputs = [{'name': name, 'type': 'str'}]
    spec = write_spec(tmp_path, example_spec(**tool_changes(1, inputs=inputs)))
    target = tmp_path / 'out'

    assert scaffold(spec, target) == 2
    assert not target.exists()


@pytest.mark.parametrize(
    'changes',
    [
        {'name': '../x'},
        {'name': '/etc/x'},
        {'name': 'Bad_Name'},
        {'name': 'trailing\n'},
        {'package': '../x'},
        {'package': '/etc/x'},
        {'package': 'class'},
        tool_changes(0, name='../x'),
        tool_changes(0, name='/etc/x'),
        {'resources': [{'uri': 'repo://{a}', 'name': '../x'}]},
        {'prompts': [{'name': 'ok', 'template': '{__import__}'}]},
    ],
)
def test_names_that_become_paths_or_code_are_rejected_before_any_write(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    target = tmp_path / 'out'

    assert scaffold(write_spec(tmp_path, example_spec(**changes)), target) == 2
    assert not target.exists()


def test_plan_that_escapes_the_target_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / 'out'
    plan = {'ok.txt': 'fine', '../escape.txt': 'bad'}

    with pytest.raises(CannotCheckError, match='outside'):
        write_project(target, plan, force=False)
    assert not target.exists()
    assert not (tmp_path / 'escape.txt').exists()


def test_symlink_in_a_forced_target_cannot_redirect_a_write(tmp_path: Path) -> None:
    outside = tmp_path / 'outside'
    outside.mkdir()
    target = tmp_path / 'out'
    target.mkdir()
    (target / 'config').symlink_to(outside, target_is_directory=True)

    with pytest.raises(CannotCheckError, match='outside'):
        write_project(target, {'config/mcp.plugin.json': '{}'}, force=True)
    assert list(outside.iterdir()) == []


def test_spec_values_are_not_printed_by_a_rejection_or_a_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = write_spec(tmp_path, example_spec(description=CANARY, package=CANARY))
    assert scaffold(bad, tmp_path / 'bad') == 2
    good = write_spec(tmp_path, example_spec(description=CANARY))
    assert scaffold(good, tmp_path / 'good') == 0

    captured = capsys.readouterr()
    assert CANARY not in captured.out + captured.err


@pytest.mark.parametrize(
    ('spec_text', 'reason'),
    [('{not json', 'not valid JSON'), ('[]', 'JSON object'), ('{"name": "a"}', 'tool')],
)
def test_spec_it_rejects_exits_two_with_a_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], spec_text: str, reason: str
) -> None:
    spec = tmp_path / 'spec.json'
    spec.write_text(spec_text)

    assert scaffold(spec, tmp_path / 'out') == 2
    assert reason in capsys.readouterr().err


def test_missing_spec_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert scaffold(tmp_path / 'absent.json', tmp_path / 'out') == 2
    assert 'cannot read the spec' in capsys.readouterr().err


def test_missing_template_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = scaffold(EXAMPLE_SPEC, tmp_path / 'out', '--template', str(tmp_path / 'absent'))

    assert code == 2
    assert 'is not a directory' in capsys.readouterr().err


def test_non_empty_target_needs_force(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / 'out'
    target.mkdir()
    (target / 'keep.txt').write_text('mine')

    assert scaffold(EXAMPLE_SPEC, target) == 2
    assert '--force' in capsys.readouterr().err
    assert list(target.iterdir()) == [target / 'keep.txt']
    assert scaffold(EXAMPLE_SPEC, target, '--force') == 0
    assert (target / 'keep.txt').read_text() == 'mine'


def test_force_replaces_a_stale_src_tree(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)
    stale = target / 'src' / 'repo_inspector' / 'tools' / 'removed_tool'
    stale.mkdir()

    assert scaffold(EXAMPLE_SPEC, target, '--force') == 0
    assert not stale.exists()


def test_spec_text_is_substituted_once_and_cannot_break_out_of_a_docstring(
    tmp_path: Path,
) -> None:
    description = 'uses __NAME__ and """ with a \\ backslash'
    target = scaffolded(
        tmp_path, description=description, **tool_changes(0, description=description)
    )

    assert 'uses __NAME__ and' in (target / 'README.md').read_text()
    for path in target.rglob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
    assert 'description = "uses __NAME__' in (target / 'pyproject.toml').read_text()


def test_template_pyproject_is_valid_toml() -> None:
    project = tomllib.loads((TEMPLATE / 'pyproject.toml').read_text())['project']

    assert project['description'] == '__DESCRIPTION_TOML__'


def test_description_round_trips_through_the_generated_pyproject(tmp_path: Path) -> None:
    description = 'says "hi" with a \\ backslash and \U0001f600'
    target = scaffolded(tmp_path, description=description)

    project = tomllib.loads((target / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    assert project['description'] == description
