"""`verify run`: execute approved contract commands without a shell and record their receipts.

The runner takes ids only and looks each one up in the ticket's contract, so nothing outside
what the user approved can run through it. Every run gets a receipt with the exit code,
duration, bounded output tails, a digest of the full output, and the HEAD it ran at.
"""

import hashlib
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from mightymodels_plugin.db.checkout import open_checkout
from mightymodels_plugin.models.contract import Outcome, Phase
from mightymodels_plugin.models.slug import Slug
from mightymodels_plugin.services.clock import now
from mightymodels_plugin.services.contract import Approved, Receipt, approved, record
from mightymodels_plugin.services.git import resolve_head

TAIL_LINES = 40
TAIL_CHARS = 4000
HEAD_MOVED = '\nHEAD changed during verification; rerun at the current HEAD.'

type RunFailure = subprocess.TimeoutExpired | FileNotFoundError


@dataclass(slots=True, kw_only=True, frozen=True)
class Execution:
    outcome: Outcome
    exit: int | None
    stdout: str
    stderr: str


@dataclass(slots=True, kw_only=True, frozen=True)
class RunRequest:
    ids: tuple[str, ...] | None
    phase: Phase


@dataclass(slots=True, kw_only=True, frozen=True)
class RunResult:
    text: str
    passed: bool


def tail(text: str) -> str:
    return '\n'.join(text.splitlines()[-TAIL_LINES:])[-TAIL_CHARS:]


def failed_execution(failure: RunFailure, command: Approved) -> Execution:
    if isinstance(failure, FileNotFoundError):
        return Execution(outcome=Outcome.NOT_FOUND, exit=None, stdout='', stderr=str(failure))
    output = failure.stdout if isinstance(failure.stdout, str) else ''
    return Execution(
        outcome=Outcome.TIMEOUT,
        exit=None,
        stdout=output,
        stderr=f'timed out after {command.timeout}s',
    )


def execute(command: Approved, root: Path) -> Execution:
    try:
        completed = subprocess.run(  # noqa: S603 - argv comes only from the user-approved contract, never from the caller
            list(command.argv),
            cwd=root,
            capture_output=True,
            text=True,
            timeout=command.timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as failure:
        return failed_execution(failure, command)
    passed = completed.returncode == command.expect_exit
    return Execution(
        outcome=Outcome.PASSED if passed else Outcome.FAILED,
        exit=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def at_one_head(execution: Execution, head: str | None, root: Path) -> Execution:
    if resolve_head(root) == head:
        return execution
    return Execution(
        outcome=Outcome.FAILED,
        exit=execution.exit,
        stdout=execution.stdout,
        stderr=execution.stderr + HEAD_MOVED,
    )


def receipt_for(command: Approved, root: Path, phase: Phase) -> Receipt:
    head = resolve_head(root)
    started = time.monotonic()
    result = at_one_head(execute(command, root), head, root)
    elapsed = int((time.monotonic() - started) * 1000)
    return Receipt(
        id=command.id,
        argv=command.argv,
        outcome=result.outcome,
        exit=result.exit,
        duration_ms=elapsed,
        stdout_tail=tail(result.stdout),
        stderr_tail=tail(result.stderr),
        digest=hashlib.sha256((result.stdout + result.stderr).encode()).hexdigest(),
        head=head,
        phase=phase,
        at=now(),
    )


def describe(receipt: Receipt) -> str:
    seconds = receipt.duration_ms / 1000
    line = f'{receipt.id} {receipt.outcome} exit={receipt.exit} {seconds:.1f}s\n'
    if receipt.outcome is Outcome.PASSED:
        return line
    detail = receipt.stderr_tail or receipt.stdout_tail
    return line + ''.join(f'  | {text}\n' for text in detail.splitlines())


def run_approved(root: Path, slug: Slug, request: RunRequest) -> RunResult:
    with open_checkout(root) as checkout:
        commands = approved(checkout, slug, request.ids)
    receipts = [receipt_for(command, root, request.phase) for command in commands]
    with open_checkout(root) as checkout:
        record(checkout, slug, receipts)
    return RunResult(
        text=''.join(describe(receipt) for receipt in receipts),
        passed=all(receipt.outcome is Outcome.PASSED for receipt in receipts),
    )
