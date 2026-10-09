"""The hook command is a sh wrapper that denies a worker, and never the main conversation, when
the Python process behind it fails."""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

WRAPPER = Path(__file__).parent.parent.joinpath('bin', 'mightymodels-dispatch-hook')
LAUNCHER_VARIABLE = 'MIGHTYMODELS_DISPATCH_LAUNCHER'
WORKER_INPUT = '{"agent_type": "mightymodels:engineer", "tool_input": {"subagent_type": "x"}}'
MAIN_INPUT = '{"tool_name": "Agent", "tool_input": {"subagent_type": "x"}}'
UNREADABLE_WORKER_INPUT = '{"agent_type": "engineer"'
UNREADABLE_MAIN_INPUT = '{"tool_name": "Agent"'
DENIED_ON_FAILURE = 2
FAILURES = {
    'exit-1': 'exit 1',
    'exit-2': 'echo partial; echo rejected >&2; exit 2',
    'killed': 'kill -9 $$',
    'missing': None,
}


@dataclass(slots=True, kw_only=True, frozen=True)
class Outcome:
    code: int
    stdout: str
    stderr: str


async def spawn_wrapper(launcher: Path, text: str) -> Outcome:
    process = await asyncio.create_subprocess_exec(
        WRAPPER,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, LAUNCHER_VARIABLE: str(launcher)},
    )
    stdout, stderr = await process.communicate(text.encode())
    return Outcome(code=process.returncode or 0, stdout=stdout.decode(), stderr=stderr.decode())


def run_wrapper(launcher: Path, text: str) -> Outcome:
    return asyncio.run(spawn_wrapper(launcher, text))


def launcher_running(directory: Path, body: str | None) -> Path:
    launcher = directory.joinpath('launcher')
    if body is not None:
        launcher.write_text(f'#!/bin/sh\n{body}\n', encoding='utf-8')
        launcher.chmod(0o755)
    return launcher


@pytest.fixture(params=FAILURES, ids=list(FAILURES))
def failing_launcher(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    return launcher_running(tmp_path, FAILURES[request.param])


class TestWrapperFile:
    def test_is_an_executable_posix_sh_script(self) -> None:
        assert os.access(WRAPPER, os.X_OK)
        assert WRAPPER.read_text(encoding='utf-8').splitlines()[0] == '#!/bin/sh'


class TestFailingLauncher:
    @pytest.mark.parametrize('text', [WORKER_INPUT, UNREADABLE_WORKER_INPUT])
    def test_input_with_an_agent_type_exits_2_with_one_line_on_stderr(
        self, failing_launcher: Path, text: str
    ) -> None:
        outcome = run_wrapper(failing_launcher, text)

        assert outcome.code == DENIED_ON_FAILURE
        assert outcome.stdout == ''
        assert len(outcome.stderr.splitlines()) == 1
        assert 'dispatch hook could not run' in outcome.stderr

    @pytest.mark.parametrize('text', [MAIN_INPUT, UNREADABLE_MAIN_INPUT, ''])
    def test_input_with_no_agent_type_exits_0_and_prints_nothing(
        self, failing_launcher: Path, text: str
    ) -> None:
        assert run_wrapper(failing_launcher, text) == Outcome(code=0, stdout='', stderr='')


class TestSucceedingLauncher:
    @pytest.mark.parametrize('text', [WORKER_INPUT, MAIN_INPUT])
    def test_passes_the_launchers_stdout_through(self, tmp_path: Path, text: str) -> None:
        launcher = launcher_running(tmp_path, 'printf \'{"decision": "%s"}\\n\' "$1"')

        assert run_wrapper(launcher, text) == Outcome(
            code=0, stdout='{"decision": "dispatch-hook"}\n', stderr=''
        )

    def test_keeps_the_hook_input_for_the_launcher(self, tmp_path: Path) -> None:
        launcher = launcher_running(tmp_path, 'cat')

        assert run_wrapper(launcher, WORKER_INPUT).stdout == f'{WORKER_INPUT}\n'

    def test_prints_nothing_when_the_launcher_prints_nothing(self, tmp_path: Path) -> None:
        launcher = launcher_running(tmp_path, 'exit 0')

        assert run_wrapper(launcher, WORKER_INPUT) == Outcome(code=0, stdout='', stderr='')
