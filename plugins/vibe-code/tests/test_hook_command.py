import json
import os
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from vibe_code_cli.builtin import Services, parse_report
from vibe_code_cli.cli import main
from vibe_code_cli.findings import Finding, error, warning
from vibe_code_cli.hook.tests.support import (
    ALLOW,
    HookRoot,
    ScriptRoot,
    Staging,
    StagingRecorder,
    command_handler,
    pre_tool_use,
)

type ServicesFactory = Callable[[Sequence[Finding]], Services]


class TestUsage:
    OPTIONS = ('--expect-exit', '--expect-field', '--expect-silent', '--malformed', '--timeout')

    def test_validate_help_shows_the_file_and_strict(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['hook', 'validate', '--help'])

        assert exit_info.value.code == 0
        output = capsys.readouterr().out
        assert 'HOOKS_FILE' in output
        assert '--strict' in output

    def test_test_help_shows_every_option(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['hook', 'test', '--help'])

        assert exit_info.value.code == 0
        output = capsys.readouterr().out
        for option in self.OPTIONS:
            assert option in output

    def test_create_hooks_without_a_command_prints_usage_and_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['hook']) == 2
        assert 'usage: vibe-code' in capsys.readouterr().err


class TestBuiltinFindings:
    CAMEL_CASE_FINDING = (warning('hooks.preToolUse: unknown hook event'),)
    BUILTIN_ERROR = (error('Unknown hook type "bogus"'),)
    BUILTIN_WARNING = (warning('unknown hook event'),)

    @pytest.fixture
    def pascal_case(self) -> dict[str, object]:
        return {'Stop': [{'hooks': [command_handler('true')]}]}

    @pytest.fixture
    def camel_case(self) -> dict[str, object]:
        return {'preToolUse': pre_tool_use(command_handler())['PreToolUse']}

    def test_clean_plugin_file_exits_zero(
        self,
        hook_clean_plugin: Path,
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert main(['hook', 'validate', str(hook_clean_plugin)], fake_services(())) == 0
        assert 'PASS' in capsys.readouterr().out

    def test_settings_file_with_other_keys_and_pascal_case_events_exits_zero(
        self,
        hook_root: HookRoot,
        hook_other_keys: dict[str, object],
        pascal_case: dict[str, object],
        fake_services: ServicesFactory,
    ) -> None:
        path = hook_root.write_settings(pascal_case, **hook_other_keys)

        assert main(['hook', 'validate', str(path)], fake_services(())) == 0

    def test_ch_a24_camel_case_event_exits_one_without_strict(
        self,
        hook_root: HookRoot,
        camel_case: dict[str, object],
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = hook_root.write_plugin(camel_case)

        assert main(['hook', 'validate', str(path)], fake_services(self.CAMEL_CASE_FINDING)) == 1
        assert 'spell it PreToolUse' in capsys.readouterr().out

    def test_builtin_error_exits_one(
        self, hook_clean_plugin: Path, fake_services: ServicesFactory
    ) -> None:
        services = fake_services(self.BUILTIN_ERROR)

        assert main(['hook', 'validate', str(hook_clean_plugin)], services) == 1

    def test_warning_exits_zero_and_strict_turns_it_into_one(
        self, hook_clean_plugin: Path, fake_services: ServicesFactory
    ) -> None:
        services = fake_services(self.BUILTIN_WARNING)
        path = str(hook_clean_plugin)

        assert main(['hook', 'validate', path], services) == 0
        assert main(['hook', 'validate', path, '--strict'], services) == 1


class TestPrintedErrorLines:
    BOTH_PASSES_WHERE = 'hooks.PreToolUse.0.hooks.0'
    BUILTIN_ONLY = (error('hooks: hooks.PreToolUse.0: Hook matcher must be an object'),)
    TWO_FAILING_FINDINGS = (
        error('hooks: hooks.PreToolUse.0.hooks.1: Invalid command hook'),
        error('hooks: hooks.PreToolUse.0.hooks.10: Invalid command hook'),
    )
    BAD_GROUP_FINDINGS = (error('hooks: hooks.PreToolUse.0.hooks.0: Invalid command hook'),)

    @pytest.fixture
    def both_passes_hooks(self) -> dict[str, object]:
        return {'PreToolUse': [{'matcher': 'Bash', 'hooks': [command_handler(bogus=1)]}]}

    @pytest.fixture
    def two_failing_hooks(self) -> dict[str, object]:
        handlers = [command_handler(), command_handler(bogus=1)]
        handlers.extend(command_handler() for _ in range(8))
        handlers.append(command_handler(bogus=2))
        return {'PreToolUse': [{'matcher': 'Bash', 'hooks': handlers}]}

    @pytest.fixture
    def bad_group_hooks(self) -> dict[str, object]:
        return {'PreToolUse': [{'matcher': 7, 'hooks': [command_handler()]}]}

    def error_lines(
        self, path: Path, services: Services, capsys: pytest.CaptureFixture[str]
    ) -> list[str]:
        assert main(['hook', 'validate', str(path)], services) == 1
        return [line for line in capsys.readouterr().out.splitlines() if line.startswith('error')]

    def test_a_handler_both_passes_report_prints_one_line(
        self,
        hook_root: HookRoot,
        both_passes_hooks: dict[str, object],
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        where = self.BOTH_PASSES_WHERE
        services = fake_services((error(f'hooks: {where}: Invalid command hook'),))

        lines = self.error_lines(hook_root.write_plugin(both_passes_hooks), services, capsys)

        assert lines == [f'error: {where}: Object contains unknown field `bogus`']

    def test_a_builtin_finding_at_a_location_the_schema_did_not_report_still_prints(
        self,
        hook_clean_plugin: Path,
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        lines = self.error_lines(hook_clean_plugin, fake_services(self.BUILTIN_ONLY), capsys)

        assert lines == ['error: hooks: hooks.PreToolUse.0: Hook matcher must be an object']

    def test_two_handlers_that_each_fail_print_one_line_each(
        self,
        hook_root: HookRoot,
        two_failing_hooks: dict[str, object],
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        services = fake_services(self.TWO_FAILING_FINDINGS)

        lines = self.error_lines(hook_root.write_plugin(two_failing_hooks), services, capsys)

        assert lines == [
            'error: hooks.PreToolUse.0.hooks.1: Object contains unknown field `bogus`',
            'error: hooks.PreToolUse.0.hooks.10: Object contains unknown field `bogus`',
        ]

    def test_a_groups_schema_finding_does_not_drop_its_handlers_builtin_findings(
        self,
        hook_root: HookRoot,
        bad_group_hooks: dict[str, object],
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        services = fake_services(self.BAD_GROUP_FINDINGS)

        lines = self.error_lines(hook_root.write_plugin(bad_group_hooks), services, capsys)

        assert lines == [
            'error: hooks.PreToolUse.0: Expected `str`, got `int` - at `$.matcher`',
            'error: hooks: hooks.PreToolUse.0.hooks.0: Invalid command hook',
        ]


class TestStaging:
    @pytest.fixture
    def recorder(self) -> StagingRecorder:
        return StagingRecorder()

    def test_plugin_file_is_staged_as_it_is_without_a_manifest_finding(
        self, hook_clean_plugin: Path, recorder: StagingRecorder
    ) -> None:
        services = Services(run_builtin=recorder)

        assert main(['hook', 'validate', str(hook_clean_plugin)], services) == 0
        assert recorder.stagings == [
            Staging(hooks=hook_clean_plugin.read_text(), manifest=True, include_manifest=False)
        ]

    def test_settings_file_is_staged_as_its_hooks_object_alone(
        self, hook_root: HookRoot, hook_other_keys: dict[str, object], recorder: StagingRecorder
    ) -> None:
        hooks = pre_tool_use(command_handler())
        path = hook_root.write_settings(hooks, **hook_other_keys)

        assert main(['hook', 'validate', str(path)], Services(run_builtin=recorder)) == 0
        assert [
            (json.loads(staging.hooks), staging.include_manifest) for staging in recorder.stagings
        ] == [({'hooks': hooks}, False)]


class TestTargetThatCannotBeChecked:
    NOT_JSON = '{"hooks": '
    NO_HOOKS_KEY = '{"model": "x"}'

    @pytest.fixture
    def settings_json(self, tmp_path: Path) -> Path:
        return tmp_path / 'settings.json'

    @pytest.fixture
    def no_claude_on_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('PATH', str(tmp_path))

    @pytest.fixture
    def unreadable_plugin(self, hook_clean_plugin: Path) -> Path:
        hook_clean_plugin.chmod(0)
        if os.access(hook_clean_plugin, os.R_OK):
            pytest.skip('this user can read a mode 000 file')
        return hook_clean_plugin

    def test_settings_file_that_is_not_json_exits_two_without_a_verdict(
        self,
        settings_json: Path,
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        settings_json.write_text(self.NOT_JSON)

        assert main(['hook', 'validate', str(settings_json)], fake_services(())) == 2
        captured = capsys.readouterr()
        assert 'not a JSON object' in captured.err
        assert 'PASS' not in captured.out
        assert 'FAIL' not in captured.out

    def test_settings_file_without_a_hooks_key_exits_two(
        self,
        settings_json: Path,
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        settings_json.write_text(self.NO_HOOKS_KEY)

        assert main(['hook', 'validate', str(settings_json)], fake_services(())) == 2
        assert 'no top-level "hooks" key' in capsys.readouterr().err

    def test_builtin_that_cannot_run_exits_two(
        self,
        hook_clean_plugin: Path,
        unavailable_services: Services,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert main(['hook', 'validate', str(hook_clean_plugin)], unavailable_services) == 2
        assert 'PASS' not in capsys.readouterr().out

    def test_path_that_is_not_a_file_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['hook', 'validate', str(tmp_path)]) == 2
        assert 'is not a file' in capsys.readouterr().err

    @pytest.mark.usefixtures('no_claude_on_path')
    def test_without_claude_on_path_exits_two_naming_claude(
        self, hook_clean_plugin: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['hook', 'validate', str(hook_clean_plugin)]) == 2
        captured = capsys.readouterr()
        assert 'claude is not on PATH' in captured.err
        assert 'PASS' not in captured.out

    def test_unreadable_file_exits_two_naming_the_path(
        self, unreadable_plugin: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['hook', 'validate', str(unreadable_plugin)]) == 2
        captured = capsys.readouterr()
        assert str(unreadable_plugin) in captured.err
        assert 'FAIL' not in captured.out


class TestParseReport:
    BUILTIN_REPORT = (
        '{"success": true, "manifest": {"errors": [], "warnings": [{"message": "no version"}]}, '
        '"contents": [{"type": "hooks", "errors": [{"message": "bad hook"}], "warnings": []}]}'
    )

    def test_parse_report_can_leave_out_the_manifest_findings(self) -> None:
        assert parse_report(self.BUILTIN_REPORT) == [warning('no version'), error('bad hook')]
        assert parse_report(self.BUILTIN_REPORT, include_manifest=False) == [error('bad hook')]


@pytest.mark.skipif(shutil.which('claude') is None, reason='needs the claude CLI')
class TestRealBuiltin:
    @pytest.fixture
    def bogus_type(self) -> dict[str, object]:
        return {
            'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'type': 'bogus', 'command': 'true'}]}]
        }

    def assert_reported_once_beside_the_builtin(
        self, path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['hook', 'validate', str(path)]) == 1
        output = capsys.readouterr().out
        assert output.count('hooks.PreToolUse.0.hooks.0') == 1
        assert "Invalid value 'bogus'" in output
        assert 'version' not in output

    def test_a_bogus_handler_type_in_a_plugin_file_is_reported_once_beside_the_real_builtin(
        self,
        hook_root: HookRoot,
        bogus_type: dict[str, object],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self.assert_reported_once_beside_the_builtin(hook_root.write_plugin(bogus_type), capsys)

    def test_a_bogus_handler_type_in_a_settings_file_is_reported_once_beside_the_real_builtin(
        self,
        hook_root: HookRoot,
        hook_other_keys: dict[str, object],
        bogus_type: dict[str, object],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self.assert_reported_once_beside_the_builtin(
            hook_root.write_settings(bogus_type, **hook_other_keys), capsys
        )


class TestExpectations:
    PRINTS_ALLOW = f'print(json.dumps({ALLOW}))'
    EXITS_ONE = 'print("no", file=sys.stderr); sys.exit(1)'
    BLOCKS = 'print("blocked: rm", file=sys.stderr); sys.exit(2)'
    EXITS_TWO = 'sys.exit(2)'
    SLEEPS = 'import time; time.sleep(30)'
    STRICT_JSON = (
        'import json, sys\ntry:\n    json.load(sys.stdin)\nexcept ValueError:\n    sys.exit(2)\n'
    )
    DOTTED_OUTPUT = (
        "print(json.dumps({'continue': False, 'hookSpecificOutput': {'n': 3, 's': 'a'}}))"
    )
    PASSING_FIELDS = (
        'hookSpecificOutput.s=a',
        'hookSpecificOutput.n=3',
        'continue=false',
        'hookSpecificOutput',
    )
    FAILING_FIELDS = ('hookSpecificOutput.s=b', 'missing')

    def test_hook_that_prints_the_contract_passes(
        self, hook_scripts: ScriptRoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        script = hook_scripts.write_script(self.PRINTS_ALLOW)

        assert hook_scripts.run(script, hook_scripts.write_payload()) == 0
        assert 'PASS hook.py < payload.json' in capsys.readouterr().out

    def test_wrong_exit_code_exits_one_and_explains_non_blocking_codes(
        self, hook_scripts: ScriptRoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        script = hook_scripts.write_script(self.EXITS_ONE)

        assert hook_scripts.run(script, hook_scripts.write_payload()) == 1
        output = capsys.readouterr().out
        assert 'exit 1, expected 0' in output
        assert 'only exit 2 blocks' in output
        assert 'stderr: no' in output

    def test_ch_a34_block_with_exit_two_passes_when_expected_and_fails_when_not(
        self, hook_scripts: ScriptRoot
    ) -> None:
        script = hook_scripts.write_script(self.BLOCKS)
        payload = hook_scripts.write_payload()

        assert hook_scripts.run(script, payload, '--expect-exit', '2') == 0
        assert hook_scripts.run(script, payload) == 1

    def test_ch_a34_exit_two_on_an_event_that_ignores_it_fails(
        self, hook_scripts: ScriptRoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        script = hook_scripts.write_script(self.EXITS_TWO)
        payload = hook_scripts.write_payload('PermissionRequest')

        assert hook_scripts.run(script, payload, '--expect-exit', '2') == 1
        assert 'does not block on PermissionRequest' in capsys.readouterr().out

    def test_hook_that_outlives_the_timeout_exits_one(
        self, hook_scripts: ScriptRoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        script = hook_scripts.write_script(self.SLEEPS)

        assert hook_scripts.run(script, hook_scripts.write_payload(), '--timeout', '0.5') == 1
        assert 'timed out after 0.5 s' in capsys.readouterr().out

    def test_malformed_sends_invalid_json_instead_of_the_payload(
        self, tmp_path: Path, hook_scripts: ScriptRoot
    ) -> None:
        script = tmp_path / 'strict.py'
        script.write_text(self.STRICT_JSON)
        payload = hook_scripts.write_payload()

        assert hook_scripts.run(script, payload, '--malformed', '--expect-exit', '2') == 0
        assert hook_scripts.run(script, payload, '--expect-exit', '0') == 0

    def test_expect_silent_passes_on_empty_stdout_and_fails_on_output(
        self, hook_scripts: ScriptRoot
    ) -> None:
        payload = hook_scripts.write_payload()
        quiet = hook_scripts.write_script('pass', 'quiet.py')
        noisy = hook_scripts.write_script(self.PRINTS_ALLOW, 'noisy.py')

        assert hook_scripts.run(quiet, payload, '--expect-silent') == 0
        assert hook_scripts.run(noisy, payload, '--expect-silent') == 1

    def test_expect_field_checks_dotted_keys_and_json_values(
        self, hook_scripts: ScriptRoot
    ) -> None:
        script = hook_scripts.write_script(self.DOTTED_OUTPUT)
        payload = hook_scripts.write_payload()

        for field in self.PASSING_FIELDS:
            assert hook_scripts.run(script, payload, '--expect-field', field) == 0
        for field in self.FAILING_FIELDS:
            assert hook_scripts.run(script, payload, '--expect-field', field) == 1

    def test_expect_field_with_an_empty_key_is_a_usage_error(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['hook', 'test', 's.py', 'p.json', '--expect-field', '=x'])

        assert exit_info.value.code == 2


class TestPlainTextStdout:
    BRANCH = 'print("Branch: main")'
    CONTEXT_EVENTS = ('SessionStart', 'UserPromptSubmit', 'UserPromptExpansion', 'PostModelSwitch')
    PROGRESS_LINES = 'print(json.dumps({"type": "progress"})); print(json.dumps({"a": 1}))'
    LOOKS_LIKE_JSON = 'print("{not json}")'
    EVENT_FROM_PAYLOAD = 'print("context" if payload["hook_event_name"] == "SessionStart" else "")'

    def test_ch_c36_plain_text_stdout_passes_for_the_context_events(
        self, hook_scripts: ScriptRoot
    ) -> None:
        script = hook_scripts.write_script(self.BRANCH)

        for event in self.CONTEXT_EVENTS:
            assert hook_scripts.run(script, hook_scripts.write_payload(event)) == 0

    @pytest.mark.parametrize(
        'event',
        [
            pytest.param('PreToolUse', id='PreToolUse'),
            pytest.param('PostToolUse', id='PostToolUse'),
            pytest.param('Stop', id='Stop'),
            pytest.param(None, id='None'),
        ],
    )
    def test_ch_c36_plain_text_stdout_fails_on_every_other_event(
        self, hook_scripts: ScriptRoot, capsys: pytest.CaptureFixture[str], event: str | None
    ) -> None:
        script = hook_scripts.write_script(self.BRANCH)

        assert hook_scripts.run(script, hook_scripts.write_payload(event)) == 1
        assert 'plain-text stdout is not read as context' in capsys.readouterr().out

    def test_ch_c36_progress_lines_are_not_skipped(
        self, hook_scripts: ScriptRoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        script = hook_scripts.write_script(self.PROGRESS_LINES)

        assert hook_scripts.run(script, hook_scripts.write_payload()) == 1
        assert 'not one JSON object' in capsys.readouterr().out

    def test_ch_a32_stdout_that_looks_like_json_but_does_not_parse_fails(
        self, hook_scripts: ScriptRoot
    ) -> None:
        script = hook_scripts.write_script(self.LOOKS_LIKE_JSON)

        assert hook_scripts.run(script, hook_scripts.write_payload('SessionStart')) == 1

    def test_ch_a38_the_event_comes_from_the_payload_with_no_event_flag(
        self, hook_scripts: ScriptRoot
    ) -> None:
        script = hook_scripts.write_script(self.EVENT_FROM_PAYLOAD)

        assert hook_scripts.run(script, hook_scripts.write_payload('SessionStart')) == 0


class TestScriptLaunch:
    BASH_BLOCKS = 'cat >/dev/null\nexit 2\n'
    DIRECT_SCRIPT = '#!/bin/sh\ncat >/dev/null\n'
    BASH_EXITS = 'exit 0\n'
    NOT_JSON = '{not json'

    @pytest.fixture
    def empty_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('PATH', str(tmp_path / 'empty'))

    @pytest.mark.skipif(shutil.which('bash') is None, reason='needs bash')
    def test_shell_script_runs_through_bash(self, tmp_path: Path, hook_scripts: ScriptRoot) -> None:
        script = tmp_path / 'hook.sh'
        script.write_text(self.BASH_BLOCKS)

        assert hook_scripts.run(script, hook_scripts.write_payload(), '--expect-exit', '2') == 0

    def test_script_with_no_known_suffix_runs_directly(
        self, tmp_path: Path, hook_scripts: ScriptRoot
    ) -> None:
        script = tmp_path / 'hook'
        script.write_text(self.DIRECT_SCRIPT)
        script.chmod(0o755)

        assert hook_scripts.run(script, hook_scripts.write_payload(), '--expect-silent') == 0

    @pytest.mark.usefixtures('empty_path')
    def test_script_whose_interpreter_is_missing_exits_two(
        self, tmp_path: Path, hook_scripts: ScriptRoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        script = tmp_path / 'hook.sh'
        script.write_text(self.BASH_EXITS)

        assert hook_scripts.run(script, hook_scripts.write_payload()) == 2
        captured = capsys.readouterr()
        assert 'bash is not on PATH' in captured.err
        assert 'PASS' not in captured.out

    def test_missing_script_exits_two(
        self, tmp_path: Path, hook_scripts: ScriptRoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert hook_scripts.run(tmp_path / 'absent.py', hook_scripts.write_payload()) == 2
        assert 'script not found' in capsys.readouterr().err

    def test_missing_payload_exits_two(
        self, tmp_path: Path, hook_scripts: ScriptRoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        script = hook_scripts.write_script('pass')

        assert hook_scripts.run(script, tmp_path / 'absent.json') == 2
        assert 'could not read payload' in capsys.readouterr().err

    def test_payload_that_is_not_json_exits_two(
        self, tmp_path: Path, hook_scripts: ScriptRoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        script = hook_scripts.write_script('pass')
        payload = tmp_path / 'payload.json'
        payload.write_text(self.NOT_JSON)

        assert hook_scripts.run(script, payload) == 2
        captured = capsys.readouterr()
        assert 'is not JSON' in captured.err
        assert 'FAIL' not in captured.out
