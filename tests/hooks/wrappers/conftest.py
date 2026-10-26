import asyncio
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping

HOOKS_DIR = Path(__file__).resolve().parents[3] / 'hooks'
FAILING_LAUNCHER = 'exit 1'
HANGING_LAUNCHER = 'exec sleep 30'
SUCCEEDING_LAUNCHER = 'printf "{}"'
SHORT_TIMER = '0.3'


@dataclass(slots=True, kw_only=True, frozen=True)
class Outcome:
    code: int
    stdout: str
    stderr: str


@dataclass(slots=True, kw_only=True, frozen=True)
class WrapperRunner:
    script: Path
    workdir: Path
    launcher_variable: str
    timer_variable: str | None = None

    def write_launcher(self, body: str) -> Path:
        launcher = self.workdir / 'stub-launcher'
        launcher.write_text(f'#!/bin/sh\n{body}\n', 'utf-8')
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
        return launcher

    def environment(self, launcher: Path, *, with_ticket_dir: bool) -> Mapping[str, str]:
        project = self.workdir / 'project'
        project.mkdir(exist_ok=True)
        if with_ticket_dir:
            (project / '.mightymodels').mkdir(exist_ok=True)
        env = {**os.environ, self.launcher_variable: str(launcher)}
        env['CLAUDE_PROJECT_DIR'] = str(project)
        if self.timer_variable is not None:
            env[self.timer_variable] = SHORT_TIMER
        return env

    async def invoke(self, args: tuple[str, ...], stdin: str, env: Mapping[str, str]) -> Outcome:
        process = await asyncio.create_subprocess_exec(
            'sh',
            str(self.script),
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=dict(env),
        )
        stdout, stderr = await process.communicate(stdin.encode())
        return Outcome(code=process.returncode or 0, stdout=stdout.decode(), stderr=stderr.decode())

    def run(
        self,
        launcher_body: str,
        payload: Mapping[str, object],
        *,
        args: tuple[str, ...] = (),
        with_ticket_dir: bool = False,
    ) -> Outcome:
        launcher = self.write_launcher(launcher_body)
        env = self.environment(launcher, with_ticket_dir=with_ticket_dir)
        return asyncio.run(self.invoke(args, json.dumps(payload), env))


@pytest.fixture
def hook_runner(tmp_path: Path) -> WrapperRunner:
    return WrapperRunner(
        script=HOOKS_DIR / 'hook.sh',
        workdir=tmp_path,
        launcher_variable='MIGHTYMODELS_HOOK_LAUNCHER',
    )


@pytest.fixture
def dispatch_runner(tmp_path: Path) -> WrapperRunner:
    return WrapperRunner(
        script=HOOKS_DIR / 'dispatch-hook.sh',
        workdir=tmp_path,
        launcher_variable='MIGHTYMODELS_DISPATCH_LAUNCHER',
        timer_variable='MIGHTYMODELS_DISPATCH_SECONDS',
    )


@pytest.fixture
def main_thread_runner(tmp_path: Path) -> WrapperRunner:
    return WrapperRunner(
        script=HOOKS_DIR / 'main-thread-hook.sh',
        workdir=tmp_path,
        launcher_variable='MIGHTYMODELS_MAIN_THREAD_LAUNCHER',
        timer_variable='MIGHTYMODELS_MAIN_THREAD_SECONDS',
    )
