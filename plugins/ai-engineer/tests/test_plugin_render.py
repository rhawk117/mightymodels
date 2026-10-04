import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from ai_engineer_cli.cli import main
from ai_engineer_cli.plugin.phases import PHASES

EXAMPLE = Path(__file__).parent.parent / 'skills' / 'plan-plugin' / 'assets' / 'plan.example.json'
RESIDUE = re.compile(r'agent-plugins|\.agent\.md|ask_user|worker', re.IGNORECASE)

KIND_COMPONENTS = {
    'skill': 'add-route',
    'command': 'ship-it',
    'agent': 'test-runner',
    'hook': 'uv-runner',
    'mcp': 'db-tools',
    'lsp': 'pyright',
    'executable': 'lint-all',
    'output-style': 'terse',
}

PLAN = {
    'name': 'py-harness',
    'description': 'Python conventions for Claude Code sessions.',
    'keywords': ['python'],
    'problem': 'Agents skip ruff.',
    'audience': {'who': 'the team', 'how': 'team'},
    'kinds': ['ecosystem'],
    'ecosystem': 'python',
    'distribution': {'channel': 'local'},
    'author': {'name': 'Platform Team'},
    'components': [{'kind': 'skill', 'name': 'add-route', 'purpose': 'Add a route.'}],
}


def all_kinds() -> list[dict[str, object]]:
    return [
        {'kind': kind, 'name': name, 'purpose': f'The {name} {kind}.'}
        for kind, name in KIND_COMPONENTS.items()
    ]


def write_plan(directory: Path, **changes: object) -> Path:
    path = directory / 'plan.json'
    path.write_text(json.dumps({**PLAN, **changes}))
    return path


def render(plan: Path, target: Path, *options: str) -> int:
    return main(['plugin', 'render', str(plan), str(target), *options])


def manifest_of(target: Path) -> dict[str, object]:
    return json.loads((target / '.claude-plugin' / 'plugin.json').read_text())


def directories_of(target: Path) -> set[str]:
    return {path.relative_to(target).as_posix() for path in target.rglob('*') if path.is_dir()}


def claude_validate(target: Path) -> subprocess.CompletedProcess[str]:
    claude = shutil.which('claude')
    if claude is None:
        pytest.skip('claude is not on PATH')
    return subprocess.run(  # noqa: S603  # fixed argument list with no shell; target is a tmp path
        [claude, 'plugin', 'validate', '--strict', str(target)],
        capture_output=True,
        text=True,
        check=False,
    )


def plan_md(tmp_path: Path, **changes: object) -> str:
    assert render(write_plan(tmp_path, **changes), tmp_path / 'out') == 0
    return (tmp_path / 'out' / 'PLAN.md').read_text()


def test_render_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['plugin', 'render', '--help'])

    assert exit_info.value.code == 0
    assert '--force' in capsys.readouterr().out


def test_pp_a9_a15_b1_b4_render_of_the_example_passes_claude_validate(tmp_path: Path) -> None:
    target = tmp_path / 'py-harness'

    assert render(EXAMPLE, target) == 0

    for name in ('.claude-plugin/plugin.json', 'README.md', 'PLAN.md', 'plugin-plan.json'):
        assert (target / name).is_file()
    assert not (target / 'plugin.json').exists()
    assert claude_validate(target).returncode == 0


def test_pp_a9_manifest_has_no_schema_and_carries_the_identity_fields(tmp_path: Path) -> None:
    assert render(EXAMPLE, tmp_path / 'out') == 0

    manifest = manifest_of(tmp_path / 'out')
    assert '$schema' not in manifest
    assert list(manifest)[:5] == ['name', 'version', 'description', 'keywords', 'author']
    assert manifest['author'] == {'name': 'Platform Team', 'email': 'platform@example.com'}
    assert manifest['license'] == 'MIT'


def test_pp_a9_manifest_omits_license_and_homepage_the_record_does_not_set(
    tmp_path: Path,
) -> None:
    assert render(write_plan(tmp_path), tmp_path / 'out') == 0

    manifest = manifest_of(tmp_path / 'out')
    for key in ('license', 'homepage', 'repository', 'userConfig', 'dependencies'):
        assert key not in manifest


def test_pp_a9_b3_b4_b12_manifest_carries_the_optional_keys_the_record_sets(
    tmp_path: Path,
) -> None:
    option = {'type': 'string', 'title': 'Token', 'description': 'API token.', 'sensitive': True}
    plan = write_plan(
        tmp_path,
        license='Apache-2.0',
        homepage='https://example.com/docs',
        userConfig={'api_token': option},
        dependencies=['base-tools', {'name': 'lint', 'marketplace': 'team'}],
    )

    assert render(plan, tmp_path / 'out') == 0

    manifest = manifest_of(tmp_path / 'out')
    assert manifest['license'] == 'Apache-2.0'
    assert manifest['homepage'] == 'https://example.com/docs'
    assert manifest['userConfig'] == {'api_token': option}
    assert manifest['dependencies'] == ['base-tools', {'name': 'lint', 'marketplace': 'team'}]
    assert claude_validate(tmp_path / 'out').returncode == 0


def test_pp_a13_render_creates_one_directory_per_planned_component_kind(tmp_path: Path) -> None:
    plan = write_plan(tmp_path, components=all_kinds())

    assert render(plan, tmp_path / 'out') == 0

    assert directories_of(tmp_path / 'out') == {
        '.claude-plugin',
        'skills',
        'skills/add-route',
        'skills/ship-it',
        'hooks',
        'agents',
        'mcp',
        'mcp/db-tools',
        'bin',
        'output-styles',
    }
    assert claude_validate(tmp_path / 'out').returncode == 0


def test_pp_a13_a_built_component_creates_no_directory(tmp_path: Path) -> None:
    built = {'kind': 'agent', 'name': 'test-runner', 'purpose': 'Run tests.', 'status': 'built'}

    assert (
        render(write_plan(tmp_path, components=[*PLAN['components'], built]), tmp_path / 'out') == 0
    )

    assert 'agents' not in directories_of(tmp_path / 'out')


def test_pp_a11_a17_plan_md_keeps_the_human_and_agent_sections_and_greppable_lines(
    tmp_path: Path,
) -> None:
    assert render(EXAMPLE, tmp_path / 'out') == 0

    text = (tmp_path / 'out' / 'PLAN.md').read_text()
    assert '\n## Human\n' in text
    assert '\n## Agent\n' in text
    for line in (
        'plugin.name: py-harness',
        'phase.1: Foundation; sessions: uv-runner',
        'component.test-runner.kind: agent',
        'component.uv-runner.builder: create-hooks',
        'component.add-fastapi-route.status: planned',
    ):
        assert f'\n{line}\n' in text


def test_pp_a48_phases_order_the_executable_before_skills_and_agents_last(
    tmp_path: Path,
) -> None:
    text = plan_md(tmp_path, components=all_kinds())

    sessions = dict(re.findall(r'^component\.([\w-]+)\.session: (\S+)$', text, re.MULTILINE))
    assert sessions['uv-runner'].startswith('1.')
    assert sessions['lint-all'] < sessions['add-route'] < sessions['test-runner']
    assert sessions['test-runner'].startswith(str(PHASES[2].number))
    assert sessions['test-runner'] > sessions['ship-it'] > sessions['add-route']


def test_pp_a22_ready_prompts_open_with_the_namespaced_builder(tmp_path: Path) -> None:
    text = plan_md(tmp_path, components=all_kinds())

    assert '\n/ai-engineer:create-skill Create the `add-route` skill' in text
    assert '\n/ai-engineer:create-hooks Create the `uv-runner` hook' in text
    assert '\n/ai-engineer:create-subagent Create the `test-runner` agent' in text
    assert '\n/ai-engineer:create-mcp Create the `db-tools` MCP server' in text
    assert '\nAdd the `pyright` language server entry to .lsp.json' in text


def test_pp_a18_marketplace_channel_adds_the_marketplace_before_the_install(
    tmp_path: Path,
) -> None:
    assert render(EXAMPLE, tmp_path / 'out') == 0

    readme = (tmp_path / 'out' / 'README.md').read_text()
    add = 'claude plugin marketplace add <source>'
    install = 'claude plugin install py-harness@platform-tools --scope project'
    assert readme.index(add) < readme.index(install)


def test_pp_a18_marketplace_channel_without_an_install_line_uses_the_plugin_name(
    tmp_path: Path,
) -> None:
    text = plan_md(tmp_path, distribution={'channel': 'marketplace'})

    assert 'claude plugin install py-harness@<marketplace> --scope project' in text


def test_pp_a18_local_channel_installs_with_plugin_dir(tmp_path: Path) -> None:
    text = plan_md(tmp_path)

    assert '\nplugin.install: claude --plugin-dir ./py-harness\n' in text
    assert 'marketplace add' not in text


def test_pp_a17_a21_verify_session_names_the_claude_code_checks(tmp_path: Path) -> None:
    text = plan_md(tmp_path)

    for command in (
        'claude plugin validate',
        '--strict',
        'claude --plugin-dir',
        '/reload-plugins',
        '/mcp',
        '/hooks',
    ):
        assert command in text.split('Verify the plugin at')[1].split('```')[0]


def test_pp_a19_a20_publish_session_pins_sha_beside_ref(tmp_path: Path) -> None:
    assert render(EXAMPLE, tmp_path / 'out') == 0

    publish = (tmp_path / 'out' / 'PLAN.md').read_text().split('Publish the plugin at')[1]
    publish = publish.split('```')[0]
    assert '.claude-plugin/marketplace.json' in publish
    assert '`ref` and the 40-char `sha`' in publish
    assert 'CLAUDE_CODE_PLUGIN_CACHE_DIR' in publish


def test_pp_a47_rendered_example_text_has_no_residue(tmp_path: Path) -> None:
    assert render(EXAMPLE, tmp_path / 'out') == 0

    for name in ('PLAN.md', 'README.md'):
        assert RESIDUE.findall((tmp_path / 'out' / name).read_text()) == []


@pytest.mark.parametrize('name', ['a/b', '..', '.hidden', '../up', 'a\\b'])
def test_pp_a13_render_refuses_a_component_name_that_could_leave_the_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    component = {'kind': 'skill', 'name': name, 'purpose': 'x'}

    assert render(write_plan(tmp_path, components=[component]), tmp_path / 'out') == 1
    assert 'error: component' in capsys.readouterr().out
    assert not (tmp_path / 'out').exists()


def test_render_refuses_a_record_that_fails_validate_and_writes_nothing(tmp_path: Path) -> None:
    assert render(write_plan(tmp_path, name='claude-x'), tmp_path / 'out') == 1
    assert not (tmp_path / 'out').exists()


def test_render_refuses_an_unreadable_record_with_exit_two(tmp_path: Path) -> None:
    assert render(tmp_path / 'missing.json', tmp_path / 'out') == 2


def test_render_refuses_an_existing_manifest_unless_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = write_plan(tmp_path)
    assert render(plan, tmp_path / 'out') == 0
    manifest = tmp_path / 'out' / '.claude-plugin' / 'plugin.json'
    manifest.write_text('{"name": "kept"}')

    assert render(plan, tmp_path / 'out') == 1
    assert '--force' in capsys.readouterr().err
    assert manifest.read_text() == '{"name": "kept"}'

    assert render(plan, tmp_path / 'out', '--force') == 0
    assert manifest_of(tmp_path / 'out')['name'] == 'py-harness'


def test_force_rewrites_the_plan_files_and_deletes_nothing(tmp_path: Path) -> None:
    plan = write_plan(tmp_path)
    assert render(plan, tmp_path / 'out') == 0
    own_skill = tmp_path / 'out' / 'skills' / 'add-route' / 'SKILL.md'
    own_skill.write_text('mine')
    stray = tmp_path / 'out' / 'notes.txt'
    stray.write_text('keep')

    assert render(write_plan(tmp_path, version='0.2.0'), tmp_path / 'out', '--force') == 0

    assert own_skill.read_text() == 'mine'
    assert stray.read_text() == 'keep'
    assert manifest_of(tmp_path / 'out')['version'] == '0.2.0'


def test_every_path_render_writes_resolves_inside_the_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / 'out'

    assert render(write_plan(tmp_path, components=all_kinds()), target) == 0

    written = [line.removeprefix('wrote ') for line in capsys.readouterr().out.splitlines()]
    written = [line for line in written if not line.startswith(('PASS', 'warning'))]
    assert len(written) == 4 + 7
    for relative in written:
        assert (target / relative).resolve().is_relative_to(target.resolve())


def test_render_refuses_a_plan_directory_that_links_out_of_the_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = tmp_path / 'outside'
    outside.mkdir()
    target = tmp_path / 'out'
    target.mkdir()
    (target / '.claude-plugin').symlink_to(outside)

    assert render(write_plan(tmp_path), target) == 1
    assert 'resolves outside' in capsys.readouterr().err
    assert list(outside.iterdir()) == []


def test_render_refuses_a_target_that_is_a_file(tmp_path: Path) -> None:
    target = tmp_path / 'out'
    target.write_text('x')

    assert render(write_plan(tmp_path), target) == 1
    assert target.read_text() == 'x'
