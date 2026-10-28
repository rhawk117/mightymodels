"""The contract run use case: runs approved commands and records a receipt for each.

The argv comes only from the ticket's contract, never from the caller, and runs without a shell.
Every run gets a receipt with the exit code, duration, bounded output tails, a digest of the full
output and the HEAD it ran at. A command that cannot be launched, outlives its timeout or prints
what is not text still gets a receipt: no exit code, whatever it printed before the failure, and
the cause as the last line of stderr. A run that HEAD moved under cannot pass.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import redact
from mightymodels_core.process import FailedRun

from .records import Receipt

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from mightymodels_core.git import Git
    from mightymodels_core.primitives import Clock, Slug
    from mightymodels_core.process import CompletedRun, FailureKind, ProcessRunner
    from mightymodels_core.vocabulary.contract import Outcome, Phase

    from .records import RecordedCommand
    from .services import ContractService

TAIL_LINES = 40
TAIL_CHARS = 4000
HEAD_MOVED = '\nHEAD changed during verification; rerun at the current HEAD.'
FAILURE_OUTCOMES: dict[FailureKind, Outcome] = {
    'timed_out': 'timeout',
    'not_found': 'not-found',
    'refused': 'refused',
    'undecodable': 'undecodable',
}


@dataclass(slots=True, kw_only=True, frozen=True)
class RunRequest:
    slug: Slug
    asked: Sequence[str] | None
    phase: Phase


@dataclass(slots=True, kw_only=True, frozen=True)
class RunResult:
    receipts: list[Receipt]

    @property
    def is_passing(self) -> bool:
        return all(receipt.outcome == 'pass' for receipt in self.receipts)


@dataclass(slots=True, kw_only=True, frozen=True)
class Execution:
    outcome: Outcome
    exit: int | None
    stdout: str
    stderr: str

    def after_head_moved(self) -> Execution:
        return Execution(
            outcome='fail', exit=self.exit, stdout=self.stdout, stderr=self.stderr + HEAD_MOVED
        )


def tail(text: str) -> str:
    return '\n'.join(text.splitlines()[-TAIL_LINES:])[-TAIL_CHARS:]


def with_cause(captured: str, cause: str) -> str:
    separator = '' if not captured or captured.endswith('\n') else '\n'
    return f'{captured}{separator}{cause}'


def execution_of(command: RecordedCommand, run: CompletedRun | FailedRun) -> Execution:
    if isinstance(run, FailedRun):
        return Execution(
            outcome=FAILURE_OUTCOMES[run.kind],
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
class ContractRunner:
    service: ContractService
    processes: ProcessRunner
    git: Git
    clock: Clock
    root: Path

    async def run(self, request: RunRequest) -> RunResult:
        commands = self.service.pick(request.slug, request.asked)
        receipts = [await self.receipt_for(command, request.phase) for command in commands]
        self.service.record(request.slug, receipts)
        return RunResult(receipts=receipts)

    async def receipt_for(self, command: RecordedCommand, phase: Phase) -> Receipt:
        head = await self.git.resolve_head()
        started = time.monotonic()
        run = await self.processes.run(command.argv, timeout=command.timeout, cwd=self.root)
        execution = execution_of(command, run)
        if await self.git.resolve_head() != head:
            execution = execution.after_head_moved()

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
