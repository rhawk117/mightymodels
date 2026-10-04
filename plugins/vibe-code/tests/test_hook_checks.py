import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from vibe_code_cli.findings import CannotCheckError, Finding, error, warning
from vibe_code_cli.hook.matchers import regex_problem
from vibe_code_cli.hook.tests.support import (
    SCRIPT_COMMAND,
    HookRoot,
    command_handler,
    pre_tool_use,
)

type FindingAssertion = Callable[[Sequence[Finding], str], None]


class TestPluginFileTopLevel:
    HANDLER = pre_tool_use(command_handler())

    def test_clean_plugin_file_has_no_findings(self, hook_root: HookRoot) -> None:
        assert hook_root.check_plugin(self.HANDLER) == []

    def test_h6_unknown_top_level_field_in_a_plugin_file_is_an_error(
        self, hook_root: HookRoot, assert_error: FindingAssertion
    ) -> None:
        findings = hook_root.check_plugin(self.HANDLER, bogus=1)

        assert_error(findings, "unknown top-level field 'bogus'")

    def test_h6_does_not_fire_on_the_other_keys_of_a_settings_file(
        self, hook_root: HookRoot, hook_other_keys: dict[str, object]
    ) -> None:
        path = hook_root.write_settings(pre_tool_use(command_handler('true')), **hook_other_keys)

        assert hook_root.check(path) == []

    def test_ch_a23_version_key_is_unknown_in_a_plugin_file(
        self, hook_root: HookRoot, assert_error: FindingAssertion
    ) -> None:
        findings = hook_root.check_plugin(self.HANDLER, version=1)

        assert_error(findings, "unknown top-level field 'version'")

    def test_h6_allows_the_description_of_a_plugin_file(self, hook_root: HookRoot) -> None:
        findings = hook_root.check_plugin(self.HANDLER, description='Formats')

        assert findings == []


class TestHooksObjectAndEvents:
    @pytest.fixture
    def empty_event(self) -> dict[str, object]:
        return {'PreToolUse': []}

    @pytest.fixture
    def camel_case(self) -> dict[str, object]:
        return {'preToolUse': pre_tool_use(command_handler())['PreToolUse']}

    @pytest.fixture
    def pascal_case(self) -> dict[str, object]:
        return {'Stop': [{'hooks': [command_handler('true')]}]}

    @pytest.fixture
    def not_an_event(self) -> dict[str, object]:
        return {'notAnEvent': [{'hooks': [command_handler('true')]}]}

    def test_h8b_empty_hooks_object_is_an_error(
        self, hook_root: HookRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(hook_root.check_plugin({}), 'must not be an empty object')

    def test_h11a_empty_event_array_is_an_error(
        self, hook_root: HookRoot, empty_event: dict[str, object], assert_error: FindingAssertion
    ) -> None:
        assert_error(
            hook_root.check_plugin(empty_event), 'hooks.PreToolUse: must not be an empty array'
        )

    def test_ch_a24_camel_case_event_is_an_error_naming_the_pascal_case_form(
        self, hook_root: HookRoot, camel_case: dict[str, object], assert_error: FindingAssertion
    ) -> None:
        assert_error(hook_root.check_plugin(camel_case), 'spell it PreToolUse')

    def test_ch_a24_pascal_case_events_pass(
        self, hook_root: HookRoot, pascal_case: dict[str, object]
    ) -> None:
        assert hook_root.check(hook_root.write_settings(pascal_case)) == []

    def test_ch_a24_a_name_that_is_no_event_in_any_case_is_a_schema_warning(
        self, hook_root: HookRoot, not_an_event: dict[str, object]
    ) -> None:
        assert hook_root.check_plugin(not_an_event) == [
            warning("hooks.notAnEvent: Invalid enum value 'notAnEvent'")
        ]


class TestHandlerFields:
    UNKNOWN_FIELD = pre_tool_use(command_handler(bogus=1))
    EXEC_FORM_FIELDS = pre_tool_use(
        {
            **command_handler(),
            'shell': 'bash',
            'async': True,
            'asyncRewake': True,
            'statusMessage': 'Hi',
        }
    )
    EMPTY_COMMAND = pre_tool_use(command_handler('  '))

    def test_h15_unknown_handler_field_is_an_error(self, hook_root: HookRoot) -> None:
        findings = hook_root.check_plugin(self.UNKNOWN_FIELD)

        assert findings == [
            error('hooks.PreToolUse.0.hooks.0: Object contains unknown field `bogus`')
        ]

    @pytest.mark.parametrize(
        'field',
        [
            pytest.param('env', id='env'),
            pytest.param('bash', id='bash'),
            pytest.param('powershell', id='powershell'),
            pytest.param('timeoutSec', id='timeoutSec'),
            pytest.param('cwd', id='cwd'),
            pytest.param('matcher', id='matcher'),
        ],
    )
    def test_ch_a28_launch_fields_of_the_other_host_are_unknown_handler_fields(
        self, hook_root: HookRoot, assert_error: FindingAssertion, field: str
    ) -> None:
        findings = hook_root.check_plugin(pre_tool_use(command_handler(**{field: 'x'})))

        assert_error(findings, f'unknown field `{field}`')

    def test_ch_a25_the_shell_field_and_exec_form_fields_are_known(
        self, hook_root: HookRoot
    ) -> None:
        assert hook_root.check_plugin(self.EXEC_FORM_FIELDS) == []

    def test_h18b_empty_command_is_an_error(
        self, hook_root: HookRoot, assert_error: FindingAssertion
    ) -> None:
        findings = hook_root.check_plugin(self.EMPTY_COMMAND)

        assert_error(findings, 'command must not be empty')


class TestScriptPaths:
    MISSING_SHELL_FORM = pre_tool_use(
        command_handler('python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/missing.py"')
    )
    UNQUOTED_WITH_FLAG = pre_tool_use(
        command_handler('python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check.py --fix')
    )
    MISSING_EXEC_FORM = pre_tool_use(
        command_handler('python3', args=['${CLAUDE_PLUGIN_ROOT}/hooks/scripts/missing.py'])
    )
    PRESENT_EXEC_FORM = pre_tool_use(
        command_handler('python3', args=['${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check.py'])
    )
    DIRECTORY = pre_tool_use(
        command_handler('python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/dir.py"')
    )
    ABSOLUTE_MISSING = pre_tool_use(command_handler('python3 /opt/none/x.py'))

    @pytest.fixture
    def script_that_is_a_directory(self, hook_root: HookRoot) -> None:
        (hook_root.root / 'hooks' / 'scripts' / 'dir.py').mkdir(parents=True)

    def test_h23a_missing_script_in_a_shell_form_command_is_an_error(
        self, hook_root: HookRoot, assert_error: FindingAssertion
    ) -> None:
        findings = hook_root.check_plugin(self.MISSING_SHELL_FORM)

        assert_error(findings, 'script not found at')

    def test_h23a_an_unquoted_placeholder_and_a_flag_after_the_script_are_resolved(
        self, hook_root: HookRoot
    ) -> None:
        assert hook_root.check_plugin(self.UNQUOTED_WITH_FLAG) == []

    def test_h23b_missing_script_in_exec_form_args_is_an_error(
        self, hook_root: HookRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(hook_root.check_plugin(self.MISSING_EXEC_FORM), 'script not found at')

    def test_ch_a26_exec_form_with_a_script_that_exists_passes(self, hook_root: HookRoot) -> None:
        assert hook_root.check_plugin(self.PRESENT_EXEC_FORM) == []

    @pytest.mark.usefixtures('script_that_is_a_directory')
    def test_h24_script_path_that_is_a_directory_is_an_error(
        self, hook_root: HookRoot, assert_error: FindingAssertion
    ) -> None:
        findings = hook_root.check_plugin(self.DIRECTORY)

        assert_error(findings, 'script path is not a file')

    def test_h25_absolute_script_path_that_does_not_exist_is_a_warning(
        self, hook_root: HookRoot, assert_warning: FindingAssertion
    ) -> None:
        findings = hook_root.check_plugin(self.ABSOLUTE_MISSING)

        assert_warning(findings, 'absolute script path /opt/none/x.py does not exist')


class TestScriptRoots:
    PROJECT_DIR_GATE = pre_tool_use(
        command_handler('"${CLAUDE_PROJECT_DIR}/.claude/hooks/gate.py"')
    )
    ROOTLESS_HANDLERS = (
        command_handler('python3 scripts/missing.py'),
        command_handler('python3 "${CLAUDE_PROJECT_DIR}/missing.py"'),
        command_handler('python3 "$HOME/missing.py"'),
    )

    @pytest.fixture
    def gate_settings(self, hook_root: HookRoot) -> Path:
        return hook_root.write_settings(self.PROJECT_DIR_GATE)

    @pytest.fixture
    def hooks_json(self, hook_root: HookRoot) -> Path:
        return hook_root.root / 'hooks.json'

    def test_script_rows_use_the_project_dir_for_a_settings_file_under_dot_claude(
        self, hook_root: HookRoot, gate_settings: Path, assert_error: FindingAssertion
    ) -> None:
        missing = f'script not found at {hook_root.root.resolve()}/.claude/hooks/gate.py'
        assert_error(hook_root.check(gate_settings), missing)

        (hook_root.root / '.claude' / 'hooks').mkdir()
        (hook_root.root / '.claude' / 'hooks' / 'gate.py').write_text('print()\n')

        assert hook_root.check(gate_settings) == []

    def test_script_rows_skip_a_path_whose_root_no_directory_names(
        self, hook_root: HookRoot, hooks_json: Path
    ) -> None:
        for handler in self.ROOTLESS_HANDLERS:
            hooks_json.write_text(json.dumps({'hooks': pre_tool_use(handler)}))

            assert hook_root.check(hooks_json) == []


class TestTimeouts:
    NO_TIMEOUT = pre_tool_use({'type': 'command', 'command': SCRIPT_COMMAND})
    ASYNC_NO_TIMEOUT = pre_tool_use({'type': 'command', 'command': SCRIPT_COMMAND, 'async': True})
    SLOW_ON_ENFORCEMENT_EVENT = pre_tool_use(command_handler(timeout=60))

    @pytest.fixture
    def no_timeout_on_prompt_submit(self) -> dict[str, object]:
        return {'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': SCRIPT_COMMAND}]}]}

    @pytest.fixture
    def slow_on_another_event(self) -> dict[str, object]:
        return {'PostToolUse': [{'matcher': 'Bash', 'hooks': [command_handler(timeout=60)]}]}

    def test_h28_missing_timeout_is_a_warning_naming_the_default(
        self, hook_root: HookRoot, assert_warning: FindingAssertion
    ) -> None:
        assert_warning(hook_root.check_plugin(self.NO_TIMEOUT), 'default of 600 s')

    def test_ch_a29_the_default_timeout_named_follows_the_event(
        self,
        hook_root: HookRoot,
        no_timeout_on_prompt_submit: dict[str, object],
        assert_warning: FindingAssertion,
    ) -> None:
        assert_warning(hook_root.check_plugin(no_timeout_on_prompt_submit), 'default of 30 s')

    def test_h28_async_handler_needs_no_timeout(self, hook_root: HookRoot) -> None:
        assert hook_root.check_plugin(self.ASYNC_NO_TIMEOUT) == []

    def test_h31_slow_timeout_on_an_enforcement_event_is_a_warning(
        self, hook_root: HookRoot, assert_warning: FindingAssertion
    ) -> None:
        findings = hook_root.check_plugin(self.SLOW_ON_ENFORCEMENT_EVENT)

        assert_warning(findings, 'timeout is 60 s on PreToolUse')

    def test_h31_slow_timeout_on_another_event_passes(
        self, hook_root: HookRoot, slow_on_another_event: dict[str, object]
    ) -> None:
        assert hook_root.check_plugin(slow_on_another_event) == []


class TestMatcherPresence:
    NOT_A_REGEX = pre_tool_use(command_handler(), matcher='(')
    NO_MATCHER = pre_tool_use(command_handler(), matcher=None)

    @pytest.fixture
    def matcher_on_stop(self) -> dict[str, object]:
        return {'Stop': [{'matcher': 'Bash', 'hooks': [command_handler()]}]}

    @pytest.fixture
    def no_matcher_on_stop(self) -> dict[str, object]:
        return {'Stop': [{'hooks': [command_handler()]}]}

    def test_h33_matcher_on_an_event_that_takes_none_is_a_warning(
        self,
        hook_root: HookRoot,
        matcher_on_stop: dict[str, object],
        assert_warning: FindingAssertion,
    ) -> None:
        assert_warning(hook_root.check_plugin(matcher_on_stop), 'matcher is ignored on Stop')

    def test_h34_matcher_that_is_not_a_regex_is_an_error(
        self, hook_root: HookRoot, assert_error: FindingAssertion
    ) -> None:
        findings = hook_root.check_plugin(self.NOT_A_REGEX)

        assert_error(findings, "matcher '(' is not a valid regular expression")

    def test_h35_missing_matcher_on_pre_tool_use_is_a_warning(
        self, hook_root: HookRoot, assert_warning: FindingAssertion
    ) -> None:
        findings = hook_root.check_plugin(self.NO_MATCHER)

        assert_warning(findings, 'runs on every tool call')

    def test_h35_missing_matcher_on_another_event_passes(
        self, hook_root: HookRoot, no_matcher_on_stop: dict[str, object]
    ) -> None:
        assert hook_root.check_plugin(no_matcher_on_stop) == []


class TestMatcherSyntax:
    @pytest.mark.parametrize(
        'matcher',
        [
            pytest.param('Bash', id='Bash'),
            pytest.param('Edit|Write', id='Edit|Write'),
            pytest.param('Edit, Write', id='Edit, Write'),
            pytest.param('*', id='*'),
            pytest.param('', id=''),
            pytest.param('^Notebook', id='^Notebook'),
            pytest.param('mcp__memory__.*', id='mcp__memory__.*'),
            pytest.param('^Edit$', id='^Edit$'),
        ],
    )
    def test_ch_a10_matchers_the_docs_accept_pass(self, matcher: str) -> None:
        assert regex_problem(matcher, 'PreToolUse') is None

    @pytest.mark.parametrize(
        'matcher',
        [
            pytest.param('(?<tool>Bash|Edit)\\k<tool>', id='(?<tool>Bash|Edit)\\k<tool>'),
            pytest.param('[^]', id='[^]'),
            pytest.param('[]', id='[]'),
            pytest.param('(?<=Notebook)Edit', id='(?<=Notebook)Edit'),
            pytest.param('\\p{L}+', id='\\p{L}+'),
            pytest.param('\\u{1F600}', id='\\u{1F600}'),
            pytest.param('\\cJ', id='\\cJ'),
            pytest.param('(a)\\2', id='(a)\\2'),
        ],
    )
    def test_h34_javascript_spellings_python_rejects_are_not_flagged(self, matcher: str) -> None:
        assert regex_problem(matcher, 'PreToolUse') is None

    @pytest.mark.parametrize(
        'matcher',
        [
            pytest.param('(', id='('),
            pytest.param('a(b', id='a(b'),
            pytest.param('*a', id='*a'),
            pytest.param('[a', id='[a'),
            pytest.param('a{2,1}', id='a{2,1}'),
        ],
    )
    def test_h34_patterns_both_languages_reject_are_flagged(self, matcher: str) -> None:
        assert regex_problem(matcher, 'PreToolUse') is not None

    def test_h34_hyphen_leaves_the_exact_match_set_for_the_narrow_events(self) -> None:
        assert regex_problem('a-(', 'StopFailure') is not None
        assert regex_problem('rate-limit', 'PreToolUse') is None


class TestHttpHandlers:
    EMPTY_ENV_VAR = pre_tool_use(
        {
            'type': 'http',
            'url': 'https://example.com/h',
            'timeout': 10,
            'allowedEnvVars': [''],
        }
    )
    OTHER_SCHEME = pre_tool_use({'type': 'http', 'url': 'ftp://example.com/h', 'timeout': 10})
    PLAIN_HTTP = pre_tool_use(
        {
            'type': 'http',
            'url': 'http://localhost:8080/hook',
            'timeout': 10,
            'headers': {'Authorization': 'Bearer $TOKEN'},
            'allowedEnvVars': ['TOKEN'],
        }
    )

    def test_h36d_empty_allowed_env_var_entry_is_an_error(
        self, hook_root: HookRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(hook_root.check_plugin(self.EMPTY_ENV_VAR), 'allowedEnvVars[0]')

    def test_h37_http_url_with_another_scheme_is_an_error(
        self, hook_root: HookRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(hook_root.check_plugin(self.OTHER_SCHEME), 'url must use http:// or https://')

    def test_ch_a30_http_handler_fields_and_a_plain_http_url_pass(
        self, hook_root: HookRoot
    ) -> None:
        assert hook_root.check_plugin(self.PLAIN_HTTP) == []


class TestUnparseableFile:
    @pytest.fixture
    def unparseable(self, hook_root: HookRoot) -> Path:
        path = hook_root.root / 'hooks' / 'hooks.json'
        path.parent.mkdir()
        path.write_text('{"hooks": ')
        return path

    def test_unparseable_file_the_builtin_passed_cannot_be_checked(
        self, hook_root: HookRoot, unparseable: Path
    ) -> None:
        with pytest.raises(CannotCheckError):
            hook_root.check(unparseable)
        assert hook_root.check(unparseable, builtin_errored=True) == []


class TestMalformedParts:
    @pytest.fixture
    def malformed_parts(self) -> dict[str, object]:
        return {
            'PreToolUse': [
                'x',
                {'matcher': 'a', 'hooks': 'x'},
                {'matcher': 'a', 'hooks': ['x', {'type': 'bogus', 'a': 1}]},
            ]
        }

    @pytest.fixture
    def hooks_an_array(self) -> list[object]:
        return []

    @pytest.fixture
    def event_not_an_array(self) -> dict[str, object]:
        return {'PreToolUse': 'x'}

    def test_each_malformed_part_gets_one_schema_finding(
        self, hook_root: HookRoot, malformed_parts: dict[str, object]
    ) -> None:
        findings = hook_root.check_plugin(malformed_parts)

        assert [finding.message for finding in findings] == [
            'hooks.PreToolUse.0: Expected `object`, got `str`',
            'hooks.PreToolUse.1: Expected `array`, got `str` - at `$.hooks`',
            'hooks.PreToolUse.2.hooks.0: Expected `object`, got `str`',
            "hooks.PreToolUse.2.hooks.1: Invalid value 'bogus' - at `$.type`",
        ]

    def test_a_hooks_value_that_is_not_an_object_gets_one_schema_finding(
        self, hook_root: HookRoot, hooks_an_array: list[object]
    ) -> None:
        findings = hook_root.check_plugin(hooks_an_array)

        assert [finding.message for finding in findings] == [
            'hooks: Expected `object`, got `array`'
        ]

    def test_an_event_whose_value_is_not_an_array_gets_one_schema_finding(
        self, hook_root: HookRoot, event_not_an_array: dict[str, object]
    ) -> None:
        findings = hook_root.check_plugin(event_not_an_array)

        assert [finding.message for finding in findings] == [
            'hooks.PreToolUse: Expected `array`, got `str`'
        ]


class TestHandlersBesideTheSchema:
    BAD_HANDLER = pre_tool_use(command_handler('python3 /opt/none/x.py', bogus=1))

    @pytest.fixture
    def bad_group(self) -> dict[str, object]:
        return {
            'PreToolUse': [{'matcher': 7, 'hooks': [command_handler('python3 /opt/none/x.py')]}]
        }

    @pytest.fixture
    def bad_beside_good(self) -> dict[str, object]:
        missing = command_handler('python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/missing.py"')
        return {'PreToolUse': [{'matcher': 'Bash', 'hooks': [command_handler(bogus=1), missing]}]}

    def test_a_handler_that_fails_the_schema_gets_no_gap_checks(self, hook_root: HookRoot) -> None:
        findings = hook_root.check_plugin(self.BAD_HANDLER)

        assert [finding.level for finding in findings] == ['error']

    def test_a_group_that_fails_the_schema_gets_no_gap_checks(
        self, hook_root: HookRoot, bad_group: dict[str, object]
    ) -> None:
        findings = hook_root.check_plugin(bad_group)

        assert [finding.message for finding in findings] == [
            'hooks.PreToolUse.0: Expected `str`, got `int` - at `$.matcher`'
        ]

    def test_a_valid_handler_is_checked_beside_a_handler_that_fails_the_schema(
        self, hook_root: HookRoot, bad_beside_good: dict[str, object]
    ) -> None:
        findings = hook_root.check_plugin(bad_beside_good)

        assert [finding.message.split(':')[0] for finding in findings] == [
            'hooks.PreToolUse.0.hooks.0',
            'hooks.PreToolUse.0.hooks.1',
        ]
