import json
from pathlib import Path

import pytest
from vibe_code_cli.cli import main

PLUGIN_ROOT = Path(__file__).parent.parent

MANIFEST = {
    'name': 'built-plugin',
    'version': '1.2.0',
    'description': 'A plugin that already exists.',
    'keywords': ['demo'],
    'license': 'MIT',
    'author': {'name': 'Platform Team'},
}


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def markdown(description: str, name: str | None = None) -> str:
    named = f'name: {name}\n' if name else ''
    return f'---\n{named}description: {description}\n---\nBody.\n'


def build_plugin(root: Path, manifest: dict[str, object] | None = None) -> Path:
    """A plugin holding one component of every kind."""
    write(root / '.claude-plugin' / 'plugin.json', json.dumps(manifest or MANIFEST))
    write(root / 'skills' / 'add-route' / 'SKILL.md', markdown('Add a route.'))
    write(root / 'agents' / 'sub' / 'runner.md', markdown('Run tests.', name='test-runner'))
    write(root / 'agents' / 'plain.md', markdown('Plain agent.'))
    write(root / 'commands' / 'ship-it.md', markdown('Ship it.'))
    write(root / 'hooks' / 'hooks.json', json.dumps({'hooks': {'PreToolUse': [], 'Stop': []}}))
    write(root / '.mcp.json', json.dumps({'mcpServers': {'db': {'command': 'uv', 'args': []}}}))
    write(root / '.lsp.json', json.dumps({'pyright': {'extensionToLanguage': {'.py': 'python'}}}))
    write(root / 'bin' / 'lint-all', '#!/bin/sh\n')
    write(root / 'output-styles' / 'terse.md', markdown('Short answers.'))
    return root


def inventory(plugin_dir: Path, *options: str) -> int:
    return main(['plugin', 'inventory', str(plugin_dir), *options])


def components_of(capsys: pytest.CaptureFixture[str]) -> dict[tuple[str, str], dict[str, object]]:
    record = json.loads(capsys.readouterr().out)
    return {(c['kind'], c['name']): c for c in record['components']}


def test_inventory_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['plugin', 'inventory', '--help'])

    assert exit_info.value.code == 0
    assert '--out' in capsys.readouterr().out


def test_pp_a39_inventory_records_one_built_component_per_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert inventory(build_plugin(tmp_path / 'built-plugin')) == 0

    found = components_of(capsys)
    assert set(found) == {
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
    assert {component['status'] for component in found.values()} == {'built'}
    assert found[('agent', 'test-runner')]['files'] == ['agents/sub/runner.md']
    assert found[('skill', 'add-route')]['purpose'] == 'Add a route.'
    assert found[('lsp', 'pyright')]['purpose'] == 'language server for .py'
    assert found[('hook', 'hooks')]['purpose'] == 'hooks with events: PreToolUse, Stop'


def test_pp_a39_inventory_reads_the_manifest_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert inventory(build_plugin(tmp_path / 'built-plugin')) == 0

    record = json.loads(capsys.readouterr().out)
    assert record['name'] == 'built-plugin'
    assert record['version'] == '1.2.0'
    assert record['license'] == 'MIT'
    assert record['author'] == {'name': 'Platform Team'}


def test_pp_a39_inventory_follows_a_manifest_skills_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / 'built-plugin'
    write(root / 'extra' / 'moved' / 'SKILL.md', markdown('Moved skill.'))
    write(root / '.claude-plugin' / 'plugin.json', json.dumps({**MANIFEST, 'skills': ['./extra']}))

    assert inventory(root) == 0

    found = components_of(capsys)
    assert found[('skill', 'moved')]['files'] == ['extra/moved/SKILL.md']


def test_pp_a39_inventory_reads_inline_manifest_servers_and_hooks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = {
        **MANIFEST,
        'mcpServers': {'search': {'type': 'http', 'url': 'https://example.com/mcp'}},
        'hooks': {'hooks': {'SessionStart': []}},
    }
    root = tmp_path / 'built-plugin'
    write(root / '.claude-plugin' / 'plugin.json', json.dumps(manifest))

    assert inventory(root) == 0

    found = components_of(capsys)
    assert found[('mcp', 'search')]['purpose'] == 'http server: https://example.com/mcp'
    assert found[('hook', 'hooks')]['files'] == ['.claude-plugin/plugin.json']


def test_pp_a39_inventory_ignores_a_manifest_path_that_leaves_the_plugin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path / 'outside' / 'stolen' / 'SKILL.md', markdown('Not part of the plugin.'))
    root = tmp_path / 'built-plugin'
    write(
        root / '.claude-plugin' / 'plugin.json', json.dumps({**MANIFEST, 'skills': ['../outside']})
    )

    assert inventory(root) == 0

    assert components_of(capsys) == {}


def test_inventory_out_writes_a_record_that_plugin_validate_accepts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = tmp_path / 'record.json'

    assert inventory(build_plugin(tmp_path / 'built-plugin'), '--out', str(record)) == 0

    assert f'wrote {record}' in capsys.readouterr().out
    assert main(['plugin', 'validate', str(record)]) == 0


def test_inventory_of_a_plugin_without_a_manifest_names_the_record_for_the_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / 'bare'
    write(root / 'skills' / 'only' / 'SKILL.md', markdown('Only.'))

    assert inventory(root) == 0

    assert json.loads(capsys.readouterr().out)['name'] == 'bare'


def test_inventory_of_a_missing_directory_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert inventory(tmp_path / 'missing') == 2
    assert 'is not a directory' in capsys.readouterr().err


def test_inventory_of_a_broken_manifest_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / 'broken'
    write(root / '.claude-plugin' / 'plugin.json', '{not json')

    assert inventory(root) == 2
    assert 'could not inventory' in capsys.readouterr().err


def test_inventory_of_this_plugin_lists_its_skills_and_executable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert inventory(PLUGIN_ROOT) == 0

    found = components_of(capsys)
    skills = {name for kind, name in found if kind == 'skill'}
    expected = {path.parent.name for path in (PLUGIN_ROOT / 'skills').glob('*/SKILL.md')}
    assert skills == expected
    assert ('executable', 'vibe-code') in found
