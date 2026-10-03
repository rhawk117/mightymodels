import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from ai_engineer_cli.findings import CannotCheckError, Finding
from ai_engineer_cli.hook_checks import check_hooks
from ai_engineer_cli.hook_matchers import regex_problem
from ai_engineer_cli.hooks_file import load_hooks_file

SCRIPT_COMMAND = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check.py"'


def command_handler(command: str = SCRIPT_COMMAND, **extra: object) -> dict[str, object]:
    return {'type': 'command', 'command': command, 'timeout': 10, **extra}


def pre_tool_use(handler: Mapping[str, object], matcher: str | None = 'Bash') -> dict[str, object]:
    group: dict[str, object] = {'hooks': [handler]}
    if matcher is not None:
        group['matcher'] = matcher
    return {'PreToolUse': [group]}


def write_plugin_hooks(root: Path, hooks: object, **top_level: object) -> Path:
    path = root / 'hooks' / 'hooks.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    scripts = root / 'hooks' / 'scripts'
    scripts.mkdir(exist_ok=True)
    (scripts / 'check.py').write_text('print()\n')
    path.write_text(json.dumps({'hooks': hooks, **top_level}))
    return path


def write_settings(root: Path, hooks: object, **top_level: object) -> Path:
    path = root / '.claude' / 'settings.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**top_level, 'hooks': hooks}))
    return path


def check(path: Path) -> list[Finding]:
    return check_hooks(load_hooks_file(path), builtin_errored=False)


def check_plugin(root: Path, hooks: object, **top_level: object) -> list[Finding]:
    return check(write_plugin_hooks(root, hooks, **top_level))


def levels(findings: list[Finding], fragment: str) -> list[str]:
    return [finding.level for finding in findings if fragment in finding.message]


def assert_error(findings: list[Finding], fragment: str) -> None:
    assert levels(findings, fragment) == ['error'], findings


def assert_warning(findings: list[Finding], fragment: str) -> None:
    assert levels(findings, fragment) == ['warning'], findings


def test_clean_plugin_file_has_no_findings(tmp_path: Path) -> None:
    assert check_plugin(tmp_path, pre_tool_use(command_handler())) == []


def test_h3_duplicate_json_key_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / 'hooks' / 'hooks.json'
    path.parent.mkdir()
    path.write_text('{"hooks": {"Stop": [{"hooks": []}]}, "hooks": {"Stop": []}}')

    assert_error(check(path), "duplicate JSON key 'hooks'")


def test_h6_unknown_top_level_field_in_a_plugin_file_is_an_error(tmp_path: Path) -> None:
    findings = check_plugin(tmp_path, pre_tool_use(command_handler()), bogus=1)

    assert_error(findings, "unknown top-level field 'bogus'")


def test_h6_does_not_fire_on_the_other_keys_of_a_settings_file(tmp_path: Path) -> None:
    path = write_settings(
        tmp_path, pre_tool_use(command_handler('true')), permissions={'allow': []}, model='x'
    )

    assert check(path) == []


def test_ch_a23_version_key_is_unknown_in_a_plugin_file(tmp_path: Path) -> None:
    findings = check_plugin(tmp_path, pre_tool_use(command_handler()), version=1)

    assert_error(findings, "unknown top-level field 'version'")


def test_h6_allows_the_description_of_a_plugin_file(tmp_path: Path) -> None:
    findings = check_plugin(tmp_path, pre_tool_use(command_handler()), description='Formats')

    assert findings == []


def test_h8b_empty_hooks_object_is_an_error(tmp_path: Path) -> None:
    assert_error(check_plugin(tmp_path, {}), 'must not be an empty object')


def test_h11a_empty_event_array_is_an_error(tmp_path: Path) -> None:
    assert_error(
        check_plugin(tmp_path, {'PreToolUse': []}), 'hooks.PreToolUse: must not be an empty array'
    )


def test_ch_a24_camel_case_event_is_an_error_naming_the_pascal_case_form(tmp_path: Path) -> None:
    hooks = {'preToolUse': pre_tool_use(command_handler())['PreToolUse']}

    assert_error(check_plugin(tmp_path, hooks), 'spell it PreToolUse')


def test_ch_a24_pascal_case_events_pass(tmp_path: Path) -> None:
    hooks = {'Stop': [{'hooks': [command_handler('true')]}]}

    assert check(write_settings(tmp_path, hooks)) == []


def test_ch_a24_a_name_that_is_no_event_in_any_case_is_left_to_the_builtin(tmp_path: Path) -> None:
    hooks = {'notAnEvent': [{'hooks': [command_handler('true')]}]}

    assert check_plugin(tmp_path, hooks) == []


def test_h15_unknown_handler_field_is_an_error(tmp_path: Path) -> None:
    findings = check_plugin(tmp_path, pre_tool_use(command_handler(bogus=1)))

    assert_error(findings, "unknown field 'bogus' on a command handler")


@pytest.mark.parametrize('field', ['env', 'bash', 'powershell', 'timeoutSec', 'cwd', 'matcher'])
def test_ch_a28_launch_fields_of_the_other_host_are_unknown_handler_fields(
    tmp_path: Path, field: str
) -> None:
    findings = check_plugin(tmp_path, pre_tool_use(command_handler(**{field: 'x'})))

    assert_error(findings, f"unknown field '{field}'")


def test_ch_a25_the_shell_field_and_exec_form_fields_are_known(tmp_path: Path) -> None:
    handler = command_handler()
    handler.update({'shell': 'bash', 'async': True, 'asyncRewake': True, 'statusMessage': 'Hi'})

    assert check_plugin(tmp_path, pre_tool_use(handler)) == []


def test_h18b_empty_command_is_an_error(tmp_path: Path) -> None:
    findings = check_plugin(tmp_path, pre_tool_use(command_handler('  ')))

    assert_error(findings, 'command must not be empty')


def test_h23a_missing_script_in_a_shell_form_command_is_an_error(tmp_path: Path) -> None:
    command = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/missing.py"'

    findings = check_plugin(tmp_path, pre_tool_use(command_handler(command)))

    assert_error(findings, 'script not found at')


def test_h23a_an_unquoted_placeholder_and_a_flag_after_the_script_are_resolved(
    tmp_path: Path,
) -> None:
    command = 'python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check.py --fix'

    assert check_plugin(tmp_path, pre_tool_use(command_handler(command))) == []


def test_h23b_missing_script_in_exec_form_args_is_an_error(tmp_path: Path) -> None:
    handler = command_handler('python3', args=['${CLAUDE_PLUGIN_ROOT}/hooks/scripts/missing.py'])

    assert_error(check_plugin(tmp_path, pre_tool_use(handler)), 'script not found at')


def test_ch_a26_exec_form_with_a_script_that_exists_passes(tmp_path: Path) -> None:
    handler = command_handler('python3', args=['${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check.py'])

    assert check_plugin(tmp_path, pre_tool_use(handler)) == []


def test_h24_script_path_that_is_a_directory_is_an_error(tmp_path: Path) -> None:
    (tmp_path / 'hooks' / 'scripts' / 'dir.py').mkdir(parents=True)
    command = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/dir.py"'

    findings = check_plugin(tmp_path, pre_tool_use(command_handler(command)))

    assert_error(findings, 'script path is not a file')


def test_h25_absolute_script_path_that_does_not_exist_is_a_warning(tmp_path: Path) -> None:
    findings = check_plugin(tmp_path, pre_tool_use(command_handler('python3 /opt/none/x.py')))

    assert_warning(findings, 'absolute script path /opt/none/x.py does not exist')


def test_script_rows_use_the_project_dir_for_a_settings_file_under_dot_claude(
    tmp_path: Path,
) -> None:
    hooks = pre_tool_use(command_handler('"${CLAUDE_PROJECT_DIR}/.claude/hooks/gate.py"'))
    path = write_settings(tmp_path, hooks)

    assert_error(check(path), f'script not found at {tmp_path.resolve()}/.claude/hooks/gate.py')

    (tmp_path / '.claude' / 'hooks').mkdir()
    (tmp_path / '.claude' / 'hooks' / 'gate.py').write_text('print()\n')

    assert check(path) == []


def test_script_rows_skip_a_path_whose_root_no_directory_names(tmp_path: Path) -> None:
    path = tmp_path / 'hooks.json'
    path.write_text(json.dumps({'hooks': pre_tool_use(command_handler())}))
    relative = command_handler('python3 scripts/missing.py')
    other_root = command_handler('python3 "${CLAUDE_PROJECT_DIR}/missing.py"')
    unknown_variable = command_handler('python3 "$HOME/missing.py"')

    for handler in (relative, other_root, unknown_variable):
        path.write_text(json.dumps({'hooks': pre_tool_use(handler)}))

        assert check(path) == []


def test_h28_missing_timeout_is_a_warning_naming_the_default(tmp_path: Path) -> None:
    handler = {'type': 'command', 'command': SCRIPT_COMMAND}

    assert_warning(check_plugin(tmp_path, pre_tool_use(handler)), 'default of 600 s')


def test_ch_a29_the_default_timeout_named_follows_the_event(tmp_path: Path) -> None:
    hooks = {'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': SCRIPT_COMMAND}]}]}

    assert_warning(check_plugin(tmp_path, hooks), 'default of 30 s')


def test_h28_async_handler_needs_no_timeout(tmp_path: Path) -> None:
    handler = {'type': 'command', 'command': SCRIPT_COMMAND, 'async': True}

    assert check_plugin(tmp_path, pre_tool_use(handler)) == []


def test_h31_slow_timeout_on_an_enforcement_event_is_a_warning(tmp_path: Path) -> None:
    findings = check_plugin(tmp_path, pre_tool_use(command_handler(timeout=60)))

    assert_warning(findings, 'timeout is 60 s on PreToolUse')


def test_h31_slow_timeout_on_another_event_passes(tmp_path: Path) -> None:
    hooks = {'PostToolUse': [{'matcher': 'Bash', 'hooks': [command_handler(timeout=60)]}]}

    assert check_plugin(tmp_path, hooks) == []


def test_h33_matcher_on_an_event_that_takes_none_is_a_warning(tmp_path: Path) -> None:
    hooks = {'Stop': [{'matcher': 'Bash', 'hooks': [command_handler()]}]}

    assert_warning(check_plugin(tmp_path, hooks), 'matcher is ignored on Stop')


def test_h34_matcher_that_is_not_a_regex_is_an_error(tmp_path: Path) -> None:
    findings = check_plugin(tmp_path, pre_tool_use(command_handler(), matcher='('))

    assert_error(findings, "matcher '(' is not a valid regular expression")


@pytest.mark.parametrize(
    'matcher',
    ['Bash', 'Edit|Write', 'Edit, Write', '*', '', '^Notebook', 'mcp__memory__.*', '^Edit$'],
)
def test_ch_a10_matchers_the_docs_accept_pass(matcher: str) -> None:
    assert regex_problem(matcher, 'PreToolUse') is None


@pytest.mark.parametrize(
    'matcher',
    [
        '(?<tool>Bash|Edit)\\k<tool>',
        '[^]',
        '[]',
        '(?<=Notebook)Edit',
        '\\p{L}+',
        '\\u{1F600}',
        '\\cJ',
        '(a)\\2',
    ],
)
def test_h34_javascript_spellings_python_rejects_are_not_flagged(matcher: str) -> None:
    assert regex_problem(matcher, 'PreToolUse') is None


@pytest.mark.parametrize('matcher', ['(', 'a(b', '*a', '[a', 'a{2,1}'])
def test_h34_patterns_both_languages_reject_are_flagged(matcher: str) -> None:
    assert regex_problem(matcher, 'PreToolUse') is not None


def test_h34_hyphen_leaves_the_exact_match_set_for_the_narrow_events() -> None:
    assert regex_problem('a-(', 'StopFailure') is not None
    assert regex_problem('rate-limit', 'PreToolUse') is None


def test_h35_missing_matcher_on_pre_tool_use_is_a_warning(tmp_path: Path) -> None:
    findings = check_plugin(tmp_path, pre_tool_use(command_handler(), matcher=None))

    assert_warning(findings, 'runs on every tool call')


def test_h35_missing_matcher_on_another_event_passes(tmp_path: Path) -> None:
    hooks = {'Stop': [{'hooks': [command_handler()]}]}

    assert check_plugin(tmp_path, hooks) == []


def test_h36d_empty_allowed_env_var_entry_is_an_error(tmp_path: Path) -> None:
    handler = {
        'type': 'http',
        'url': 'https://example.com/h',
        'timeout': 10,
        'allowedEnvVars': [''],
    }

    assert_error(check_plugin(tmp_path, pre_tool_use(handler)), 'allowedEnvVars[0]')


def test_h37_http_url_with_another_scheme_is_an_error(tmp_path: Path) -> None:
    handler = {'type': 'http', 'url': 'ftp://example.com/h', 'timeout': 10}

    assert_error(check_plugin(tmp_path, pre_tool_use(handler)), 'url must use http:// or https://')


def test_ch_a30_http_handler_fields_and_a_plain_http_url_pass(tmp_path: Path) -> None:
    handler = {
        'type': 'http',
        'url': 'http://localhost:8080/hook',
        'timeout': 10,
        'headers': {'Authorization': 'Bearer $TOKEN'},
        'allowedEnvVars': ['TOKEN'],
    }

    assert check_plugin(tmp_path, pre_tool_use(handler)) == []


def test_unparseable_file_the_builtin_passed_cannot_be_checked(tmp_path: Path) -> None:
    path = tmp_path / 'hooks' / 'hooks.json'
    path.parent.mkdir()
    path.write_text('{"hooks": ')

    with pytest.raises(CannotCheckError):
        check(path)
    assert check_hooks(load_hooks_file(path), builtin_errored=True) == []


def test_malformed_parts_are_left_to_the_builtin(tmp_path: Path) -> None:
    hooks = {
        'PreToolUse': [
            'x',
            {'matcher': 'a', 'hooks': 'x'},
            {'matcher': 'a', 'hooks': ['x', {'type': 'bogus', 'a': 1}]},
        ]
    }

    assert check_plugin(tmp_path, hooks) == []
    assert check_plugin(tmp_path, []) == []
