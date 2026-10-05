"""The `pythonista hooks` commands as Claude Code runs them, and lazy group loading."""

import io
import json
import subprocess
import sys
from types import MappingProxyType

import pytest
from python_harness.cli import build_parser, main, requested_groups
from python_harness.commands.domain import ProcessEdge
from python_harness.commands.exit_codes import ExitCode
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.hooks.tests.payloads import (
    bash_payload,
    session_payload,
    tool_payload,
)


def run_hook(command: str, payload: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    edge = ProcessEdge(io.StringIO(payload), stdout, stderr, MappingProxyType({}))
    exit_code = main(('hooks', command), edge=edge)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class TestGuardPython:
    def test_plain_python_gets_a_note_and_no_permission_decision(self) -> None:
        exit_code, stdout, _ = run_hook('guard-python', bash_payload('python3 -m pytest'))

        output = json.loads(stdout)['hookSpecificOutput']
        assert (exit_code, sorted(output), output['hookEventName']) == (
            ExitCode.PASSED,
            ['additionalContext', 'hookEventName'],
            'PreToolUse',
        )

    @pytest.mark.parametrize(
        'payload',
        [
            pytest.param(bash_payload('uv run python -m pytest'), id='uv-run'),
            pytest.param(tool_payload('Edit'), id='other-tool'),
        ],
    )
    def test_a_quiet_call_prints_nothing(self, payload: str) -> None:
        assert run_hook('guard-python', payload) == (ExitCode.PASSED, '', '')

    def test_an_unreadable_payload_exits_one(self) -> None:
        exit_code, stdout, stderr = run_hook('guard-python', 'not json')

        assert (exit_code, stdout, stderr.startswith('pythonista hooks: ')) == (
            ExitCode.FAILED,
            '',
            True,
        )


class TestSessionStart:
    def test_the_briefing_is_additional_context(self, project_builder: ProjectBuilder) -> None:
        project_builder.write({'pyproject.toml': '[project]\nname = "demo"\n'})
        payload = session_payload(project_builder.root.as_posix())

        exit_code, stdout, _ = run_hook('session-start', payload)

        output = json.loads(stdout)['hookSpecificOutput']
        root_line = f'- Root: {project_builder.root.as_posix()} (pyproject.toml;'
        context_lines = output['additionalContext'].splitlines()
        assert (
            exit_code,
            output['hookEventName'],
            context_lines[1][: len(root_line)],
        ) == (
            ExitCode.PASSED,
            'SessionStart',
            root_line,
        )

    def test_a_payload_for_another_event_exits_one(self) -> None:
        exit_code, _, stderr = run_hook('session-start', bash_payload('ls'))

        assert (exit_code, 'not PreToolUse' in stderr) == (ExitCode.FAILED, True)


class TestLazyGroups:
    def test_only_the_requested_group_is_loaded(self) -> None:
        assert requested_groups(('hooks', 'guard-python')) == frozenset({'hooks'})

    def test_the_guard_never_imports_the_scan(self) -> None:
        code = (
            'import sys\n'
            'from python_harness.cli import build_parser, requested_groups\n'
            "build_parser(requested_groups(['hooks', 'guard-python']))\n"
            'import python_harness.hooks.guard.services\n'
            "heavy = {'python_harness.survey.services',"
            " 'python_harness.hooks.briefing.services'}\n"
            'print(sorted(heavy & set(sys.modules)))\n'
        )

        completed = subprocess.run(  # noqa: S603  the test interpreter, with a fixed script.
            (sys.executable, '-c', code), capture_output=True, text=True, check=True
        )

        assert completed.stdout == '[]\n'

    def test_help_lists_every_group_without_loading_them(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            build_parser(()).parse_args(('--help',))

        listed = capsys.readouterr().out
        assert [name for name in ('inspect', 'hooks') if name not in listed] == []
