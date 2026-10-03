import json
import os
import shutil
from pathlib import Path

import pytest
from ai_engineer_cli import create_hooks
from ai_engineer_cli.builtin import BuiltinUnavailableError, parse_report
from ai_engineer_cli.cli import main
from ai_engineer_cli.findings import Finding, error, warning

SCRIPT_COMMAND = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check.py"'
CLEAN_HOOKS = {
    'PreToolUse': [
        {
            'matcher': 'Bash',
            'hooks': [{'type': 'command', 'command': SCRIPT_COMMAND, 'timeout': 10}],
        }
    ]
}
BOGUS_TYPE_HOOKS = {
    'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'type': 'bogus', 'command': 'true'}]}]
}
BUILTIN_REPORT = (
    '{"success": true, "manifest": {"errors": [], "warnings": [{"message": "no version"}]}, '
    '"contents": [{"type": "hooks", "errors": [{"message": "bad hook"}], "warnings": []}]}'
)


def write_plugin(root: Path, hooks: object = CLEAN_HOOKS) -> Path:
    scripts = root / 'hooks' / 'scripts'
    scripts.mkdir(parents=True)
    (scripts / 'check.py').write_text('print()\n')
    path = root / 'hooks' / 'hooks.json'
    path.write_text(json.dumps({'hooks': hooks}))
    return path


def write_settings(root: Path, hooks: object = CLEAN_HOOKS) -> Path:
    path = root / '.claude' / 'settings.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'permissions': {'allow': []}, 'model': 'x', 'hooks': hooks}))
    return path


def stub_builtin(monkeypatch: pytest.MonkeyPatch, findings: list[Finding]) -> None:
    monkeypatch.setattr(create_hooks, 'run_builtin', lambda _target, **_options: findings)


def test_validate_help_shows_the_file_and_strict(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['create-hooks', 'validate', '--help'])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert 'HOOKS_FILE' in output
    assert '--strict' in output


def test_test_help_shows_every_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['create-hooks', 'test', '--help'])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    for option in (
        '--expect-exit',
        '--expect-field',
        '--expect-silent',
        '--malformed',
        '--timeout',
    ):
        assert option in output


def test_create_hooks_without_a_command_prints_usage_and_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(['create-hooks']) == 2
    assert 'usage: ai-engineer' in capsys.readouterr().err


def test_clean_plugin_file_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch, [])

    assert main(['create-hooks', 'validate', str(write_plugin(tmp_path))]) == 0
    assert 'PASS' in capsys.readouterr().out


def test_settings_file_with_other_keys_and_pascal_case_events_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch, [])
    hooks = {'Stop': [{'hooks': [{'type': 'command', 'command': 'true', 'timeout': 10}]}]}

    assert main(['create-hooks', 'validate', str(write_settings(tmp_path, hooks))]) == 0


def test_ch_a24_camel_case_event_exits_one_without_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch, [warning('hooks.preToolUse: unknown hook event')])
    hooks = {'preToolUse': CLEAN_HOOKS['PreToolUse']}

    assert main(['create-hooks', 'validate', str(write_plugin(tmp_path, hooks))]) == 1
    assert 'spell it PreToolUse' in capsys.readouterr().out


def test_builtin_error_exits_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_builtin(monkeypatch, [error('Unknown hook type "bogus"')])

    assert main(['create-hooks', 'validate', str(write_plugin(tmp_path))]) == 1


def test_warning_exits_zero_and_strict_turns_it_into_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch, [warning('unknown hook event')])
    path = str(write_plugin(tmp_path))

    assert main(['create-hooks', 'validate', path]) == 0
    assert main(['create-hooks', 'validate', path, '--strict']) == 1


def test_plugin_file_is_staged_as_it_is_without_a_manifest_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged: dict[str, object] = {}

    def capture(target: Path, *, include_manifest: bool) -> list[Finding]:
        staged['hooks'] = (target / 'hooks' / 'hooks.json').read_text()
        staged['manifest'] = (target / '.claude-plugin' / 'plugin.json').is_file()
        staged['include_manifest'] = include_manifest
        return []

    monkeypatch.setattr(create_hooks, 'run_builtin', capture)
    path = write_plugin(tmp_path)

    assert main(['create-hooks', 'validate', str(path)]) == 0
    assert staged == {'hooks': path.read_text(), 'manifest': True, 'include_manifest': False}


def test_settings_file_is_staged_as_its_hooks_object_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged: list[object] = []

    def capture(target: Path, *, include_manifest: bool) -> list[Finding]:
        assert not include_manifest
        staged.append(json.loads((target / 'hooks' / 'hooks.json').read_text()))
        return []

    monkeypatch.setattr(create_hooks, 'run_builtin', capture)

    assert main(['create-hooks', 'validate', str(write_settings(tmp_path))]) == 0
    assert staged == [{'hooks': CLEAN_HOOKS}]


def test_settings_file_that_is_not_json_exits_two_without_a_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch, [])
    path = tmp_path / 'settings.json'
    path.write_text('{"hooks": ')

    assert main(['create-hooks', 'validate', str(path)]) == 2
    captured = capsys.readouterr()
    assert 'not a JSON object' in captured.err
    assert 'PASS' not in captured.out
    assert 'FAIL' not in captured.out


def test_settings_file_without_a_hooks_key_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch, [])
    path = tmp_path / 'settings.json'
    path.write_text('{"model": "x"}')

    assert main(['create-hooks', 'validate', str(path)]) == 2
    assert 'no top-level "hooks" key' in capsys.readouterr().err


def test_builtin_that_cannot_run_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unavailable(_target: Path, **_options: bool) -> list[Finding]:
        message = 'claude plugin validate printed no JSON report'
        raise BuiltinUnavailableError(message)

    monkeypatch.setattr(create_hooks, 'run_builtin', unavailable)

    assert main(['create-hooks', 'validate', str(write_plugin(tmp_path))]) == 2
    assert 'PASS' not in capsys.readouterr().out


def test_path_that_is_not_a_file_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(['create-hooks', 'validate', str(tmp_path)]) == 2
    assert 'is not a file' in capsys.readouterr().err


def test_without_claude_on_path_exits_two_naming_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_plugin(tmp_path)
    monkeypatch.setenv('PATH', str(tmp_path))

    assert main(['create-hooks', 'validate', str(path)]) == 2
    captured = capsys.readouterr()
    assert 'claude is not on PATH' in captured.err
    assert 'PASS' not in captured.out


def test_unreadable_file_exits_two_naming_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_plugin(tmp_path)
    path.chmod(0)
    if os.access(path, os.R_OK):
        pytest.skip('this user can read a mode 000 file')

    assert main(['create-hooks', 'validate', str(path)]) == 2
    captured = capsys.readouterr()
    assert str(path) in captured.err
    assert 'FAIL' not in captured.out


def test_parse_report_can_leave_out_the_manifest_findings() -> None:
    assert parse_report(BUILTIN_REPORT) == [warning('no version'), error('bad hook')]
    assert parse_report(BUILTIN_REPORT, include_manifest=False) == [error('bad hook')]


@pytest.mark.skipif(shutil.which('claude') is None, reason='needs the claude CLI')
def test_real_builtin_reports_a_bogus_handler_type_in_a_plugin_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_plugin(tmp_path, BOGUS_TYPE_HOOKS)

    assert main(['create-hooks', 'validate', str(path)]) == 1
    output = capsys.readouterr().out
    assert 'Unknown hook type "bogus"' in output
    assert 'version' not in output


@pytest.mark.skipif(shutil.which('claude') is None, reason='needs the claude CLI')
def test_real_builtin_reports_a_bogus_handler_type_in_a_settings_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_settings(tmp_path, BOGUS_TYPE_HOOKS)

    assert main(['create-hooks', 'validate', str(path)]) == 1
    output = capsys.readouterr().out
    assert 'Unknown hook type "bogus"' in output
    assert 'version' not in output


ALLOW = "{'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}"


def write_script(root: Path, body: str, name: str = 'hook.py') -> Path:
    path = root / name
    path.write_text(f'import json, sys\npayload = json.load(sys.stdin)\n{body}\n')
    return path


def write_payload(root: Path, event: str | None = 'PreToolUse') -> Path:
    path = root / 'payload.json'
    payload = {'session_id': 's', 'cwd': '/p', 'tool_name': 'Bash'}
    path.write_text(json.dumps({**payload, 'hook_event_name': event} if event else payload))
    return path


def run_test(script: Path, payload: Path, *options: str) -> int:
    return main(['create-hooks', 'test', str(script), str(payload), *options])


def test_hook_that_prints_the_contract_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = write_script(tmp_path, f'print(json.dumps({ALLOW}))')

    assert run_test(script, write_payload(tmp_path)) == 0
    assert 'PASS hook.py < payload.json' in capsys.readouterr().out


def test_wrong_exit_code_exits_one_and_explains_non_blocking_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = write_script(tmp_path, 'print("no", file=sys.stderr); sys.exit(1)')

    assert run_test(script, write_payload(tmp_path)) == 1
    output = capsys.readouterr().out
    assert 'exit 1, expected 0' in output
    assert 'only exit 2 blocks' in output
    assert 'stderr: no' in output


def test_ch_a34_block_with_exit_two_passes_when_expected_and_fails_when_not(
    tmp_path: Path,
) -> None:
    script = write_script(tmp_path, 'print("blocked: rm", file=sys.stderr); sys.exit(2)')
    payload = write_payload(tmp_path)

    assert run_test(script, payload, '--expect-exit', '2') == 0
    assert run_test(script, payload) == 1


def test_ch_a34_exit_two_on_an_event_that_ignores_it_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = write_script(tmp_path, 'sys.exit(2)')

    assert run_test(script, write_payload(tmp_path, 'PermissionRequest'), '--expect-exit', '2') == 1
    assert 'does not block on PermissionRequest' in capsys.readouterr().out


def test_hook_that_outlives_the_timeout_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = write_script(tmp_path, 'import time; time.sleep(30)')

    assert run_test(script, write_payload(tmp_path), '--timeout', '0.5') == 1
    assert 'timed out after 0.5 s' in capsys.readouterr().out


def test_malformed_sends_invalid_json_instead_of_the_payload(tmp_path: Path) -> None:
    script = tmp_path / 'strict.py'
    script.write_text(
        'import json, sys\ntry:\n    json.load(sys.stdin)\nexcept ValueError:\n    sys.exit(2)\n'
    )
    payload = write_payload(tmp_path)

    assert run_test(script, payload, '--malformed', '--expect-exit', '2') == 0
    assert run_test(script, payload, '--expect-exit', '0') == 0


def test_expect_silent_passes_on_empty_stdout_and_fails_on_output(tmp_path: Path) -> None:
    payload = write_payload(tmp_path)
    quiet = write_script(tmp_path, 'pass', 'quiet.py')
    noisy = write_script(tmp_path, f'print(json.dumps({ALLOW}))', 'noisy.py')

    assert run_test(quiet, payload, '--expect-silent') == 0
    assert run_test(noisy, payload, '--expect-silent') == 1


def test_expect_field_checks_dotted_keys_and_json_values(tmp_path: Path) -> None:
    script = write_script(
        tmp_path, "print(json.dumps({'continue': False, 'hookSpecificOutput': {'n': 3, 's': 'a'}}))"
    )
    payload = write_payload(tmp_path)

    assert run_test(script, payload, '--expect-field', 'hookSpecificOutput.s=a') == 0
    assert run_test(script, payload, '--expect-field', 'hookSpecificOutput.n=3') == 0
    assert run_test(script, payload, '--expect-field', 'continue=false') == 0
    assert run_test(script, payload, '--expect-field', 'hookSpecificOutput') == 0
    assert run_test(script, payload, '--expect-field', 'hookSpecificOutput.s=b') == 1
    assert run_test(script, payload, '--expect-field', 'missing') == 1


def test_expect_field_with_an_empty_key_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['create-hooks', 'test', 's.py', 'p.json', '--expect-field', '=x'])

    assert exit_info.value.code == 2


def test_ch_c36_plain_text_stdout_passes_for_the_context_events(tmp_path: Path) -> None:
    script = write_script(tmp_path, 'print("Branch: main")')

    for event in ('SessionStart', 'UserPromptSubmit', 'UserPromptExpansion', 'PostModelSwitch'):
        assert run_test(script, write_payload(tmp_path, event)) == 0


@pytest.mark.parametrize('event', ['PreToolUse', 'PostToolUse', 'Stop', None])
def test_ch_c36_plain_text_stdout_fails_on_every_other_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], event: str | None
) -> None:
    script = write_script(tmp_path, 'print("Branch: main")')

    assert run_test(script, write_payload(tmp_path, event)) == 1
    assert 'plain-text stdout is not read as context' in capsys.readouterr().out


def test_ch_c36_progress_lines_are_not_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = write_script(
        tmp_path, 'print(json.dumps({"type": "progress"})); print(json.dumps({"a": 1}))'
    )

    assert run_test(script, write_payload(tmp_path)) == 1
    assert 'not one JSON object' in capsys.readouterr().out


def test_ch_a32_stdout_that_looks_like_json_but_does_not_parse_fails(tmp_path: Path) -> None:
    script = write_script(tmp_path, 'print("{not json}")')

    assert run_test(script, write_payload(tmp_path, 'SessionStart')) == 1


def test_ch_a38_the_event_comes_from_the_payload_with_no_event_flag(tmp_path: Path) -> None:
    script = write_script(
        tmp_path,
        'print("context" if payload["hook_event_name"] == "SessionStart" else "")',
    )

    assert run_test(script, write_payload(tmp_path, 'SessionStart')) == 0


def test_shell_script_runs_through_bash(tmp_path: Path) -> None:
    if shutil.which('bash') is None:
        pytest.skip('needs bash')
    script = tmp_path / 'hook.sh'
    script.write_text('cat >/dev/null\nexit 2\n')

    assert run_test(script, write_payload(tmp_path), '--expect-exit', '2') == 0


def test_script_with_no_known_suffix_runs_directly(tmp_path: Path) -> None:
    script = tmp_path / 'hook'
    script.write_text('#!/bin/sh\ncat >/dev/null\n')
    script.chmod(0o755)

    assert run_test(script, write_payload(tmp_path), '--expect-silent') == 0


def test_script_whose_interpreter_is_missing_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / 'hook.sh'
    script.write_text('exit 0\n')
    payload = write_payload(tmp_path)
    monkeypatch.setenv('PATH', str(tmp_path / 'empty'))

    assert run_test(script, payload) == 2
    captured = capsys.readouterr()
    assert 'bash is not on PATH' in captured.err
    assert 'PASS' not in captured.out


def test_missing_script_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_test(tmp_path / 'absent.py', write_payload(tmp_path)) == 2
    assert 'script not found' in capsys.readouterr().err


def test_missing_payload_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    script = write_script(tmp_path, 'pass')

    assert run_test(script, tmp_path / 'absent.json') == 2
    assert 'could not read payload' in capsys.readouterr().err


def test_payload_that_is_not_json_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = write_script(tmp_path, 'pass')
    payload = tmp_path / 'payload.json'
    payload.write_text('{not json')

    assert run_test(script, payload) == 2
    captured = capsys.readouterr()
    assert 'is not JSON' in captured.err
    assert 'FAIL' not in captured.out
