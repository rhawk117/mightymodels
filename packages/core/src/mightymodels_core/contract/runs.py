"""The contract run use case: runs approved commands and records a receipt for each.

Each receipt is saved as soon as its command finishes, so an interrupted run keeps what it proved.
The argv comes only from the ticket's contract, never from the caller, and runs without a shell.
Every run gets a receipt with the exit code, duration, bounded output tails, a digest of the full
output and the HEAD it ran at. A command that cannot be launched, outlives its timeout or prints
what is not text still gets a receipt: no exit code, whatever it printed before the failure, and
the cause as the last line of stderr. A run that HEAD moved under cannot pass.
"""

import hashlib
import os
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

import anyio

from mightymodels_core.git import GitUnavailableError, UntrackedFiles
from mightymodels_core.primitives import redact
from mightymodels_core.process import ChildSetting, FailedRun

from .errors import TrackedChangesError
from .records import Receipt

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from contextlib import AbstractContextManager

    from mightymodels_core.git import Git
    from mightymodels_core.primitives import Clock, Slug
    from mightymodels_core.process import CompletedRun, FailureKind, ProcessRunner, RunOutcome
    from mightymodels_core.vocabulary.contract import Outcome, Phase

    from .records import ApprovalSource, RecordedCommand

TAIL_LINES = 40
TAIL_CHARS = 4000
HEAD_MOVED = '\nHEAD changed during verification; rerun at the current HEAD.'
DROPPED_VARIABLES = frozenset({'UV_PROJECT', 'UV_PROJECT_ENVIRONMENT', 'VIRTUAL_ENV'})
TREE_CHANGED = '\nTracked files changed during verification; rerun on a clean tree.'


@dataclass(slots=True, kw_only=True, frozen=True)
class RunRequest:
    slug: Slug
    asked: Sequence[str] | None
    phase: Phase


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandRun:
    receipt: Receipt
    approval_source: ApprovalSource


@dataclass(slots=True, kw_only=True, frozen=True)
class RunResult:
    runs: list[CommandRun]

    @property
    def receipts(self) -> list[Receipt]:
        return [run.receipt for run in self.runs]

    @property
    def is_passing(self) -> bool:
        return all(run.receipt.outcome == 'pass' for run in self.runs)


@dataclass(slots=True, kw_only=True, frozen=True)
class Execution:
    outcome: Outcome
    exit: int | None
    stdout: str
    stderr: str

    def failing_with(self, cause: str) -> Execution:
        return Execution(
            outcome='fail', exit=self.exit, stdout=self.stdout, stderr=self.stderr + cause
        )


def tail(text: str) -> str:
    return '\n'.join(text.splitlines()[-TAIL_LINES:])[-TAIL_CHARS:]


def with_cause(captured: str, cause: str) -> str:
    separator = '' if not captured or captured.endswith('\n') else '\n'
    return f'{captured}{separator}{cause}'


def failure_outcome(kind: FailureKind) -> Outcome:
    outcomes: dict[FailureKind, Outcome] = {
        'timed_out': 'timeout',
        'not_found': 'not-found',
        'refused': 'refused',
        'undecodable': 'undecodable',
    }
    return outcomes[kind]


def execution_of(command: RecordedCommand, run: CompletedRun | FailedRun) -> Execution:
    if isinstance(run, FailedRun):
        return Execution(
            outcome=failure_outcome(run.kind),
            exit=None,
            stdout=run.stdout,
            stderr=with_cause(run.stderr, run.detail),
        )

    return Execution(
        outcome='pass' if run.exit == command.expect_exit else 'fail',
        exit=run.exit,
        stdout=run.stdout,
        stderr=run.stderr,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class RunOptions:
    heartbeat_seconds: float = 30


type RunState = Literal['started', 'running', 'finished']


@dataclass(slots=True, kw_only=True, frozen=True)
class RunProgress:
    key: str
    position: int
    total: int
    state: RunState
    outcome: Outcome | None = None


@runtime_checkable
class RunLedger(Protocol):
    def pick(self, slug: Slug, asked: Sequence[str] | None) -> list[RecordedCommand]: ...

    def record(self, slug: Slug, receipts: Sequence[Receipt]) -> None: ...


@runtime_checkable
class RunUnit(Protocol):
    @property
    def contracts(self) -> RunLedger: ...


@runtime_checkable
class RunWork(Protocol):
    def read(self) -> AbstractContextManager[RunUnit]: ...

    def write(self) -> AbstractContextManager[RunUnit]: ...


@runtime_checkable
class RunReporter(Protocol):
    async def report(self, progress: RunProgress) -> None: ...


def child_environment(parent: Mapping[str, str]) -> dict[str, str]:
    child = {name: value for name, value in parent.items() if name not in DROPPED_VARIABLES}
    virtual_env = parent.get('VIRTUAL_ENV', '')
    if virtual_env and 'PATH' in child:
        plugin_bin = str(Path(virtual_env) / 'bin')
        entries = child['PATH'].split(os.pathsep)
        child['PATH'] = os.pathsep.join(entry for entry in entries if entry != plugin_bin)

    return child


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractRunner:
    work: RunWork
    processes: ProcessRunner
    git: Git
    clock: Clock
    root: Path
    environment: Mapping[str, str]
    reporter: RunReporter
    options: RunOptions = field(default_factory=RunOptions)

    async def run(self, request: RunRequest) -> RunResult:
        with self.work.read() as unit:
            commands = unit.contracts.pick(request.slug, request.asked)

        dirty = await self.git.dirty_paths(untracked=UntrackedFiles.NO)
        if dirty is None:
            raise GitUnavailableError(detail='git status gave no answer')

        if dirty:
            raise TrackedChangesError(paths=dirty)

        total = len(commands)
        runs = [
            await self.run_command(
                request,
                command,
                RunProgress(key=command.key, position=position, total=total, state='started'),
            )
            for position, command in enumerate(commands, start=1)
        ]
        return RunResult(runs=runs)

    async def run_command(
        self, request: RunRequest, command: RecordedCommand, started: RunProgress
    ) -> CommandRun:
        await self.notify(started)
        receipt = await self.receipt_for(command, request.phase, replace(started, state='running'))
        with self.work.write() as unit:
            unit.contracts.record(request.slug, [receipt])

        await self.notify(replace(started, state='finished', outcome=receipt.outcome))
        return CommandRun(receipt=receipt, approval_source=command.approval_source)

    async def receipt_for(
        self, command: RecordedCommand, phase: Phase, running: RunProgress
    ) -> Receipt:
        head = await self.git.resolve_head()
        started = time.monotonic()
        run = await self.launch(command, running)
        execution = execution_of(command, run)
        if await self.git.resolve_head() != head:
            execution = execution.failing_with(HEAD_MOVED)

        if await self.git.dirty_paths(untracked=UntrackedFiles.NO) != []:
            execution = execution.failing_with(TREE_CHANGED)

        elapsed = int((time.monotonic() - started) * 1000)
        return Receipt(
            key=command.key,
            argv=command.argv,
            outcome=execution.outcome,
            exit=execution.exit,
            duration_ms=elapsed,
            stdout_tail=redact(tail(execution.stdout)),
            stderr_tail=redact(tail(execution.stderr)),
            digest=hashlib.sha256((execution.stdout + execution.stderr).encode()).hexdigest(),
            head=head,
            phase=phase,
            at=self.clock.now(),
        )

    async def launch(self, command: RecordedCommand, running: RunProgress) -> RunOutcome:
        finished = anyio.Event()
        outcomes: list[RunOutcome] = []
        async with anyio.create_task_group() as group:
            group.start_soon(self.beat, running, finished)
            outcomes.append(
                await self.processes.run(
                    command.argv,
                    timeout=command.timeout,
                    setting=ChildSetting(cwd=self.root, env=self.environment),
                )
            )
            finished.set()

        return outcomes[0]

    async def beat(self, running: RunProgress, finished: anyio.Event) -> None:
        while not finished.is_set():
            with anyio.move_on_after(self.options.heartbeat_seconds):
                await finished.wait()

            if not finished.is_set():
                await self.notify(running)

    async def notify(self, progress: RunProgress) -> None:
        try:
            await self.reporter.report(progress)
        except Exception:  # noqa: BLE001  progress is best-effort; a failing reporter must never cost a command or a receipt
            return
