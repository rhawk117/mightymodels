import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from vibe_code_cli.builtin import BuiltinUnavailableError
from vibe_code_cli.cli import main
from vibe_code_cli.findings import Finding, error, warning
from vibe_code_cli.mcp import command as mcp_group
from vibe_code_cli.mcp import help_probe

STDIO_SERVER = {'command': 'uv', 'args': ['run', 'server']}
HTTP_SERVER = {'type': 'http', 'url': 'https://example.com/mcp'}
NO_COMMAND = {'mcpServers': {'db': {'type': 'stdio'}}}


def write_config(
    directory: Path, document: object = None, name: str = '.mcp.json', *, text: str | None = None
) -> Path:
    path = directory / name
    if text is None:
        text = json.dumps({'mcpServers': {'db': STDIO_SERVER}} if document is None else document)
    path.write_text(text)
    return path


def stub_builtin(monkeypatch: pytest.MonkeyPatch, findings: list[Finding] | None = None) -> None:
    monkeypatch.setattr(mcp_group, 'run_builtin', lambda _target, **_options: findings or [])


def validate(kind: str, path: Path, *options: str) -> int:
    return main(['mcp', 'validate', str(path), '--kind', kind, *options])


def servers_file(directory: Path, servers: dict[str, object], kind: str = 'plugin') -> Path:
    if kind == 'user':
        return write_config(directory, {'numStartups': 3, 'mcpServers': servers}, '.claude.json')
    return write_config(directory, {'mcpServers': servers})


def test_mc_a29_validate_help_shows_the_file_kind_and_options(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['mcp', 'validate', '--help'])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    for text in ('FILE', '--kind', 'plugin,project,user', '--check-command', '--strict'):
        assert text in output


def test_create_mcp_without_a_command_prints_usage_and_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(['mcp']) == 2
    assert 'usage: vibe-code' in capsys.readouterr().err


def test_validate_without_a_kind_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['mcp', 'validate', 'x.json'])

    assert exit_info.value.code == 2


@pytest.mark.parametrize('kind', ['plugin', 'project', 'user'])
def test_clean_file_exits_zero_for_every_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    kind: str,
) -> None:
    stub_builtin(monkeypatch)
    path = servers_file(tmp_path, {'db': STDIO_SERVER, 'api': HTTP_SERVER}, kind)

    assert validate(kind, path) == 0
    assert f'PASS {path} as {kind}' in capsys.readouterr().out


def test_builtin_error_exits_one_and_its_message_is_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch, [error('Invalid input: expected string')])

    assert validate('plugin', write_config(tmp_path)) == 1
    assert 'error: Invalid input: expected string' in capsys.readouterr().out


def test_warning_exits_zero_and_strict_turns_it_into_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch, [warning('url uses http://')])
    path = write_config(tmp_path)

    assert validate('plugin', path) == 0
    assert validate('plugin', path, '--strict') == 1


def test_file_that_is_not_a_file_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert validate('plugin', tmp_path) == 2
    captured = capsys.readouterr()
    assert 'is not a file' in captured.err
    assert 'FAIL' not in captured.out


def test_unreadable_file_exits_two_naming_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_config(tmp_path)
    path.chmod(0)
    if os.access(path, os.R_OK):
        pytest.skip('this user can read a mode 000 file')

    assert validate('plugin', path) == 2
    captured = capsys.readouterr()
    assert str(path) in captured.err
    assert 'FAIL' not in captured.out


def test_builtin_that_cannot_run_exits_two_without_a_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unavailable(_target: Path, **_options: bool) -> list[Finding]:
        message = 'claude plugin validate printed no JSON report'
        raise BuiltinUnavailableError(message)

    monkeypatch.setattr(mcp_group, 'run_builtin', unavailable)

    assert validate('plugin', write_config(tmp_path)) == 2
    captured = capsys.readouterr()
    assert 'no JSON report' in captured.err
    assert 'PASS' not in captured.out


def test_without_claude_on_path_exits_two_naming_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_config(tmp_path)
    monkeypatch.setenv('PATH', str(tmp_path))

    assert validate('plugin', path) == 2
    captured = capsys.readouterr()
    assert 'claude is not on PATH' in captured.err
    assert 'PASS' not in captured.out


def test_invalid_json_that_the_builtin_reports_exits_one_without_own_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch, [error('Invalid JSON syntax')])

    assert validate('project', write_config(tmp_path, text='{"mcpServers": ')) == 1
    assert 'must be a JSON object' not in capsys.readouterr().out


def test_invalid_json_that_the_builtin_lets_pass_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)

    assert validate('project', write_config(tmp_path, text='{"mcpServers": ')) == 2
    captured = capsys.readouterr()
    assert 'not JSON' in captured.err
    assert 'PASS' not in captured.out


def stage(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    staged: dict[str, object] = {}

    def capture(target: Path, *, include_manifest: bool) -> list[Finding]:
        staged['mcp'] = (target / '.mcp.json').read_text()
        staged['manifest'] = (target / '.claude-plugin' / 'plugin.json').is_file()
        staged['include_manifest'] = include_manifest
        return []

    monkeypatch.setattr(mcp_group, 'run_builtin', capture)
    return staged


@pytest.mark.parametrize('kind', ['plugin', 'project'])
def test_plugin_and_project_files_are_staged_as_they_are(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    staged = stage(monkeypatch)
    path = write_config(tmp_path, text='{"db": {"command": "uv"}}')

    validate(kind, path)

    assert staged == {'mcp': path.read_text(), 'manifest': True, 'include_manifest': False}


def test_user_file_is_staged_as_its_servers_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = stage(monkeypatch)

    validate('user', servers_file(tmp_path, {'db': STDIO_SERVER}, 'user'))

    assert json.loads(str(staged['mcp'])) == {'mcpServers': {'db': STDIO_SERVER}}
    assert staged['include_manifest'] is False


def test_user_file_without_servers_is_staged_with_an_empty_server_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = stage(monkeypatch)

    validate('user', write_config(tmp_path, {'numStartups': 3}, '.claude.json'))

    assert json.loads(str(staged['mcp'])) == {'mcpServers': {}}


def test_m2_top_level_array_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)

    assert validate('plugin', write_config(tmp_path, [])) == 1
    assert 'error: Expected `object`, got `array`' in capsys.readouterr().out


def test_m4_extra_top_level_key_beside_the_servers_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    path = write_config(tmp_path, {'mcpServers': {'db': STDIO_SERVER}, 'extra': 1})

    assert validate('plugin', path) == 1
    assert "unexpected top-level key 'extra'" in capsys.readouterr().out


def test_m4_does_not_fire_for_a_user_file_with_other_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch)

    assert validate('user', servers_file(tmp_path, {'db': STDIO_SERVER}, 'user')) == 0


def test_m6_servers_that_are_not_an_object_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)

    assert validate('plugin', write_config(tmp_path, {'mcpServers': []})) == 1
    assert 'error: Expected `object`, got `array` - at `$.mcpServers`' in capsys.readouterr().out


@pytest.mark.parametrize(
    ('kind', 'document'),
    [
        ('plugin', {'mcpServers': {}}),
        ('plugin', {}),
        ('project', {'mcpServers': {}}),
        ('user', {'numStartups': 3}),
    ],
)
def test_m7_file_with_no_servers_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    kind: str,
    document: object,
) -> None:
    stub_builtin(monkeypatch)

    assert validate(kind, write_config(tmp_path, document)) == 1
    assert 'no servers found' in capsys.readouterr().out


def test_m10a_unknown_key_is_an_error_in_a_plugin_and_a_warning_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    path = write_config(tmp_path, {'mcpServers': {'db': {**STDIO_SERVER, 'bogus': 1}}})

    assert validate('plugin', path) == 1
    assert validate('project', path) == 0
    assert validate('user', path, '--strict') == 1
    assert "unknown server key 'bogus'" in capsys.readouterr().out


def test_m10a_remote_server_keys_are_checked_against_the_remote_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    remote = {**HTTP_SERVER, 'command': 'uv', 'oauth': {}, 'headersHelper': 'x', 'alwaysLoad': True}

    assert validate('plugin', servers_file(tmp_path, {'api': remote})) == 1
    output = capsys.readouterr().out
    assert output.count('unknown server key') == 1
    assert "unknown server key 'command'" in output


def test_mc_a10_cwd_is_reported_as_an_unknown_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    path = write_config(tmp_path, {'mcpServers': {'db': {**STDIO_SERVER, 'cwd': '.'}}})

    assert validate('plugin', path) == 1
    assert "unknown server key 'cwd'" in capsys.readouterr().out


def test_m10b_and_mc_a7_tools_key_is_reported_with_the_permission_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    path = write_config(tmp_path, {'mcpServers': {'db': {**STDIO_SERVER, 'tools': ['*']}}})

    assert validate('plugin', path) == 1
    output = capsys.readouterr().out
    assert '"tools" is not a Claude Code server key' in output
    assert 'permissions.allow' in output
    assert "unknown server key 'tools'" not in output


def test_m23_sse_transport_is_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    path = servers_file(tmp_path, {'api': {'type': 'sse', 'url': 'https://example.com/sse'}})

    assert validate('plugin', path) == 0
    assert validate('plugin', path, '--strict') == 1
    assert 'sse transport is deprecated' in capsys.readouterr().out


def test_m25_plugin_file_not_named_dot_mcp_json_is_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    path = write_config(tmp_path, name='mcp.json')

    assert validate('plugin', path) == 0
    assert validate('plugin', path, '--strict') == 1
    assert 'mcp.json is never read as a plugin MCP config' in capsys.readouterr().out


def test_m26_project_file_not_named_dot_mcp_json_is_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    path = write_config(tmp_path, name='mcp-config.json')

    assert validate('project', path) == 0
    assert validate('project', path, '--strict') == 1
    assert 'never read as a project MCP config' in capsys.readouterr().out


def test_mc_a4_plugin_file_needs_no_schema_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)

    assert validate('plugin', write_config(tmp_path), '--strict') == 0
    assert 'PASS' in capsys.readouterr().out


def test_mc_a5_plugin_accepts_the_wrapper_and_a_bare_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch)
    wrapped = write_config(tmp_path)
    (tmp_path / 'bare').mkdir()
    bare = write_config(tmp_path / 'bare', {'db': STDIO_SERVER})

    assert validate('plugin', wrapped, '--strict') == 0
    assert validate('plugin', bare, '--strict') == 0


def test_mc_a5_project_file_without_the_wrapper_is_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    path = write_config(tmp_path, {'db': STDIO_SERVER})

    assert validate('project', path) == 0
    assert validate('project', path, '--strict') == 1
    assert 'with the mcpServers wrapper' in capsys.readouterr().out


@pytest.mark.parametrize('transport', ['stdio', 'http', 'sse', 'ws', 'streamable-http'])
def test_mc_a6_every_documented_transport_is_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    transport: str,
) -> None:
    stub_builtin(monkeypatch)
    server = {'type': transport, 'command': 'uv'}
    if transport != 'stdio':
        server = {'type': transport, 'url': 'https://example.com/mcp'}

    assert validate('plugin', servers_file(tmp_path, {'db': server})) == 0
    assert 'unknown server key' not in capsys.readouterr().out


@pytest.mark.parametrize(
    'server',
    [
        {'command': '${TOOL_BIN:-uv}'},
        {'command': 'uv', 'args': ['--root', '${CLAUDE_PLUGIN_ROOT}/x', '${OPT:-1}']},
        {'command': 'uv', 'env': {'K': '${CLAUDE_PLUGIN_DATA}', 'U': '${user_config.token}'}},
        {'type': 'http', 'url': '${API_BASE_URL:-https://example.com}/mcp'},
        {'type': 'http', 'url': 'https://example.com', 'headers': {'A': '${PROJECT_TOKEN:-none}'}},
    ],
)
def test_mc_a9_references_with_a_default_or_a_provided_name_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, server: dict[str, object]
) -> None:
    stub_builtin(monkeypatch)
    for name in ('TOOL_BIN', 'OPT', 'API_BASE_URL', 'PROJECT_TOKEN'):
        monkeypatch.delenv(name, raising=False)

    assert validate('plugin', servers_file(tmp_path, {'db': server}), '--strict') == 0


@pytest.mark.parametrize(
    ('server', 'location'),
    [
        ({'command': '${UNSET_BIN}'}, 'db.command'),
        ({'command': 'uv', 'args': ['a', '${UNSET_BIN}']}, 'db.args[1]'),
        ({'command': 'uv', 'env': {'KEY': '${UNSET_BIN}'}}, 'db.env.KEY'),
        ({'type': 'http', 'url': '${UNSET_BIN}/mcp'}, 'db.url'),
        ({'type': 'http', 'url': 'https://x', 'headers': {'H': '${UNSET_BIN}'}}, 'db.headers.H'),
    ],
)
def test_mc_a9_unset_variable_without_a_default_is_a_warning_in_every_location(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    server: dict[str, object],
    location: str,
) -> None:
    stub_builtin(monkeypatch)
    monkeypatch.delenv('UNSET_BIN', raising=False)
    path = servers_file(tmp_path, {'db': server})

    assert validate('plugin', path) == 0
    assert validate('plugin', path, '--strict') == 1
    assert f'{location}: ${{UNSET_BIN}} is not set here' in capsys.readouterr().out


def test_mc_a9_variable_that_is_set_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_builtin(monkeypatch)
    monkeypatch.setenv('SET_BIN', 'uv')

    assert (
        validate('plugin', servers_file(tmp_path, {'db': {'command': '${SET_BIN}'}}), '--strict')
        == 0
    )


def test_mc_a9_bare_dollar_variable_is_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    path = servers_file(tmp_path, {'db': {'command': 'uv', 'env': {'KEY': '$HOME/x'}}})

    assert validate('plugin', path) == 0
    assert validate('plugin', path, '--strict') == 1
    assert (
        'db.env.KEY: a bare $NAME reference is not expanded; write it as ${NAME}'
        in capsys.readouterr().out
    )


@pytest.mark.parametrize('field', ['url', 'headers'])
def test_mc_b4_credential_variable_in_a_remote_url_or_headers_is_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], field: str
) -> None:
    stub_builtin(monkeypatch)
    monkeypatch.setenv('ANTHROPIC_AUTH_TOKEN', 'real-secret')
    remote = {'type': 'http', 'url': 'https://example.com'}
    if field == 'url':
        remote['url'] = 'https://example.com/${ANTHROPIC_AUTH_TOKEN:-x}'
    else:
        remote['headers'] = {'Authorization': 'Bearer ${ANTHROPIC_AUTH_TOKEN}'}

    assert validate('plugin', servers_file(tmp_path, {'api': remote}), '--strict') == 1
    output = capsys.readouterr().out
    assert 'reads as empty in a remote server url or headers' in output
    assert 'real-secret' not in output


def test_mc_b4_credential_variable_in_a_stdio_env_is_not_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch)
    monkeypatch.setenv('NPM_TOKEN', 'x')
    server = {'command': 'uv', 'env': {'NPM_TOKEN': '${NPM_TOKEN}'}}

    assert validate('plugin', servers_file(tmp_path, {'db': server}), '--strict') == 0


def test_findings_never_print_an_env_or_headers_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    monkeypatch.delenv('NOPE', raising=False)
    servers: dict[str, object] = {
        'db': {'command': 'uv', 'env': {'K': 'hunter2-env ${NOPE} $BARE', 'bogus': 'x'}},
        'api': {'type': 'http', 'url': 'https://x', 'headers': {'A': 'hunter2-header ${NOPE}'}},
    }

    assert validate('plugin', servers_file(tmp_path, servers), '--strict') == 1
    output = capsys.readouterr().out
    assert 'NOPE' in output
    assert 'hunter2' not in output


def test_bare_variable_warning_never_prints_a_piece_of_an_env_or_headers_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    servers: dict[str, object] = {
        'db': {'command': 'uv', 'env': {'PASSWORD': 'hunter$ecretpart'}},
        'api': {'type': 'http', 'url': 'https://x', 'headers': {'A': 'Bearer tok$ecretpart'}},
    }

    assert validate('plugin', servers_file(tmp_path, servers), '--strict') == 1
    output = capsys.readouterr().out
    assert 'db.env.PASSWORD: a bare $NAME reference' in output
    assert 'api.headers.A: a bare $NAME reference' in output
    assert 'ecretpart' not in output


def command_config(directory: Path, command: str, args: list[str]) -> Path:
    return write_config(directory, {'mcpServers': {'db': {'command': command, 'args': args}}})


def test_m27_command_not_on_path_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    path = command_config(tmp_path, 'no-such-command-xyz', [])

    assert validate('plugin', path, '--check-command') == 1
    assert "command 'no-such-command-xyz' not found on PATH" in capsys.readouterr().out


def test_m28_help_that_exits_nonzero_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    path = command_config(tmp_path, sys.executable, ['-c', 'import sys; sys.exit(7)'])

    assert validate('plugin', path, '--check-command') == 1
    assert '--help exited 7' in capsys.readouterr().out


def test_m28_help_that_outlives_the_timeout_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    monkeypatch.setattr(help_probe, 'COMMAND_TIMEOUT_SECONDS', 0.5)
    path = command_config(tmp_path, sys.executable, ['-c', 'import time; time.sleep(30)'])

    assert validate('plugin', path, '--check-command') == 1
    assert '--help timed out after 0.5 s' in capsys.readouterr().out


def test_check_command_passes_when_help_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch)
    path = command_config(tmp_path, sys.executable, ['-c', 'pass'])

    assert validate('plugin', path, '--check-command') == 0


def test_check_command_runs_nothing_without_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch)
    marker = tmp_path / 'ran'
    path = command_config(
        tmp_path, sys.executable, ['-c', f'import pathlib; pathlib.Path({str(marker)!r}).touch()']
    )

    assert validate('plugin', path) == 0
    assert not marker.exists()
    assert validate('plugin', path, '--check-command') == 0
    assert marker.exists()


def test_check_command_substitutes_the_plugin_root_with_the_file_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch)
    (tmp_path / 'server.py').write_text('pass\n')
    path = command_config(tmp_path, sys.executable, ['${CLAUDE_PLUGIN_ROOT}/server.py'])

    assert validate('plugin', path, '--check-command') == 0


def test_check_command_does_not_run_a_remote_or_malformed_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch)
    servers: dict[str, object] = {
        'api': HTTP_SERVER,
        'bad': {'args': ['no-such-command-xyz']},
    }

    assert validate('plugin', servers_file(tmp_path, servers), '--check-command') == 0


def test_check_command_does_not_run_a_server_whose_value_has_the_wrong_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    servers: dict[str, object] = {'bad': {'command': 'no-such-command-xyz', 'args': 'x'}}

    assert validate('plugin', servers_file(tmp_path, servers), '--check-command') == 1
    output = capsys.readouterr().out
    assert 'Expected `array`, got `str` - at `$.mcpServers[...].args`' in output
    assert 'not found on PATH' not in output


def test_check_command_for_a_project_file_runs_in_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch)
    (tmp_path / 'server.py').write_text('pass\n')
    monkeypatch.chdir(tmp_path)
    path = command_config(tmp_path, sys.executable, ['server.py'])

    assert validate('project', path, '--check-command') == 0


@pytest.mark.skipif(shutil.which('claude') is None, reason='needs the claude CLI')
@pytest.mark.parametrize('kind', ['plugin', 'project'])
def test_real_builtin_reports_a_server_with_no_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    path = write_config(tmp_path, NO_COMMAND)

    assert validate(kind, path) == 1
    output = capsys.readouterr().out
    assert 'mcpServers.db.command: Invalid input: expected string, received undefined' in output
    assert 'version' not in output
