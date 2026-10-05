"""Verification contract, no-shell runner, and result receipts for a mightymodels ticket.

The contract lists every command a ticket may run to prove its work, each approved by
the user before it is recorded. The runner executes commands by contract id only: it
never takes an argv from its caller, so nothing outside the approved contract can run
through it. Commands run without a shell and with a timeout, and every run appends a
receipt with the exit code, duration, bounded output tails, a digest of the full output,
and the HEAD it ran at.

Usage:
    python3 verification.py contract --slug SLUG  < commands.json
    python3 verification.py run --slug SLUG (--id ID [--id ID ...] | --all)
        [--phase PHASE]
    python3 verification.py status --slug SLUG [--prefix PREFIX]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

SCHEMA_VERSION = 1
EXIT_FAILED = 1
EXIT_REJECTED = 2
DEFAULT_TIMEOUT = 300
MAX_TIMEOUT = 3600
TAIL_LINES = 40
TAIL_CHARS = 4000
SHORT_SHA = 12
COMMAND_ID = re.compile(r'^[A-Za-z0-9._-]+$')


class Command(StrEnum):
    CONTRACT = 'contract'
    RUN = 'run'
    STATUS = 'status'


class Phase(StrEnum):
    PLANNING = 'planning'
    TASK = 'task'
    REVIEW = 'review'
    LANDING = 'landing'


class Outcome(StrEnum):
    PASSED = 'pass'
    FAILED = 'fail'
    TIMEOUT = 'timeout'
    NOT_FOUND = 'not-found'


class VerificationError(Exception):
    pass


class NoRepositoryError(VerificationError):
    def __init__(self, cwd: Path) -> None:
        super().__init__(f'{cwd} is not inside a git repository')


class NoContractError(VerificationError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} does not exist; record a contract first')


class UnknownCommandError(VerificationError):
    def __init__(self, unknown: list[str]) -> None:
        super().__init__(f'not in the contract: {unknown}; approve them with contract first')


class InvalidCommandError(VerificationError):
    def __init__(self, index: int, reason: str) -> None:
        super().__init__(f'command {index}: {reason}')


class ChangedCommandError(VerificationError):
    def __init__(self, command_id: str) -> None:
        super().__init__(
            f'{command_id} is already approved with a different argv; give it a new id'
        )


class UnsupportedSchemaError(VerificationError):
    def __init__(self, path: Path, version: object) -> None:
        super().__init__(f'{path}: schema {version!r} is not supported')


class MissingApprovalError(VerificationError):
    def __init__(self) -> None:
        super().__init__('approved_by is required: who approved these commands')


@dataclass(frozen=True, slots=True)
class Approved:
    id: str
    argv: tuple[str, ...]
    expect_exit: int
    timeout: int
    approved_by: str
    approved_at: str
    head: str | None


@dataclass(frozen=True, slots=True)
class Receipt:
    id: str
    argv: tuple[str, ...]
    outcome: Outcome
    exit: int | None
    duration_ms: int
    stdout_tail: str
    stderr_tail: str
    digest: str
    head: str | None
    phase: Phase
    at: str
    schema: int = SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class Paths:
    root: Path
    slug: str

    @property
    def directory(self) -> Path:
        return self.root / '.mightymodels' / self.slug / 'verification'

    @property
    def contract(self) -> Path:
        return self.directory / 'contract.json'

    @property
    def receipts(self) -> Path:
        return self.directory / 'receipts.jsonl'


@dataclass(slots=True)
class Contract:
    commands: dict[str, Approved] = field(default_factory=dict)


def now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec='seconds')


def repository_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / '.git').exists():
            return candidate
    raise NoRepositoryError(start)


def read_text(path: Path) -> str | None:
    return path.read_text(encoding='utf-8').strip() if path.is_file() else None


def git_dir(root: Path) -> Path:
    dot_git = root / '.git'
    if dot_git.is_file():
        pointer = read_text(dot_git) or ''
        return (root / pointer.removeprefix('gitdir:').strip()).resolve()
    return dot_git


def common_dir(directory: Path) -> Path:
    pointer = read_text(directory / 'commondir')
    return (directory / pointer).resolve() if pointer else directory


def packed_ref(directory: Path, ref: str) -> str | None:
    packed = read_text(directory / 'packed-refs') or ''
    matches = (
        line.split(' ', 1)[0]
        for line in packed.splitlines()
        if line.endswith(f' {ref}') and not line.startswith(('#', '^'))
    )
    return next(matches, None)


def resolve_head(root: Path) -> str | None:
    directory = git_dir(root)
    head = read_text(directory / 'HEAD')
    if head is None or not head.startswith('ref:'):
        return head
    ref = head.removeprefix('ref:').strip()
    shared = common_dir(directory)
    return read_text(directory / ref) or read_text(shared / ref) or packed_ref(shared, ref)


def load_contract(paths: Paths) -> Contract:
    if not paths.contract.is_file():
        return Contract()
    raw = json.loads(paths.contract.read_text(encoding='utf-8'))
    if raw.get('schema') != SCHEMA_VERSION:
        raise UnsupportedSchemaError(paths.contract, raw.get('schema'))
    commands = {
        command_id: Approved(**{**entry, 'argv': tuple(entry['argv'])})
        for command_id, entry in raw['commands'].items()
    }
    return Contract(commands=commands)


def save_contract(paths: Paths, contract: Contract) -> None:
    payload = {
        'schema': SCHEMA_VERSION,
        'slug': paths.slug,
        'commands': {key: asdict(value) for key, value in contract.commands.items()},
    }
    paths.directory.mkdir(parents=True, exist_ok=True)
    temporary = paths.contract.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    temporary.replace(paths.contract)


def command_error(entry: dict[str, object]) -> str | None:
    argv = entry.get('argv')
    timeout = entry.get('timeout', DEFAULT_TIMEOUT)
    error = None
    if not isinstance(entry.get('id'), str) or not COMMAND_ID.match(str(entry['id'])):
        error = 'id must be letters, digits, dots, dashes, or underscores'
    elif not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        error = 'argv must be a non-empty list of strings; no shell string'
    elif not isinstance(timeout, int) or not 1 <= timeout <= MAX_TIMEOUT:
        error = f'timeout must be 1 to {MAX_TIMEOUT} seconds'
    elif not isinstance(entry.get('expect_exit', 0), int):
        error = 'expect_exit must be an integer'
    return error


@dataclass(frozen=True, slots=True)
class Approval:
    by: str
    at: str
    head: str | None


def approve(entry: dict[str, object], approval: Approval) -> Approved:
    argv = entry.get('argv')
    return Approved(
        id=str(entry['id']),
        argv=tuple(str(arg) for arg in argv) if isinstance(argv, list) else (),
        expect_exit=int(str(entry.get('expect_exit', 0))),
        timeout=int(str(entry.get('timeout', DEFAULT_TIMEOUT))),
        approved_by=approval.by,
        approved_at=approval.at,
        head=approval.head,
    )


def merge(contract: Contract, entries: list[dict[str, object]], approval: Approval) -> int:
    added = 0
    for index, entry in enumerate(entries):
        reason = command_error(entry)
        if reason is not None:
            raise InvalidCommandError(index, reason)
        approved = approve(entry, approval)
        existing = contract.commands.get(approved.id)
        if existing is not None and existing.argv != approved.argv:
            raise ChangedCommandError(approved.id)
        if existing is None:
            contract.commands[approved.id] = approved
            added += 1
    return added


def tail(text: str) -> str:
    return '\n'.join(text.splitlines()[-TAIL_LINES:])[-TAIL_CHARS:]


@dataclass(frozen=True, slots=True)
class Execution:
    outcome: Outcome
    exit: int | None
    stdout: str
    stderr: str


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
    except subprocess.TimeoutExpired as expired:
        output = expired.stdout if isinstance(expired.stdout, str) else ''
        return Execution(Outcome.TIMEOUT, None, output, f'timed out after {command.timeout}s')
    except FileNotFoundError as missing:
        return Execution(Outcome.NOT_FOUND, None, '', str(missing))
    passed = completed.returncode == command.expect_exit
    outcome = Outcome.PASSED if passed else Outcome.FAILED
    return Execution(outcome, completed.returncode, completed.stdout, completed.stderr)


def receipt_for(command: Approved, paths: Paths, phase: Phase) -> Receipt:
    head = resolve_head(paths.root)
    started = time.monotonic()
    result = execute(command, paths.root)
    if resolve_head(paths.root) != head:
        result = Execution(
            Outcome.FAILED,
            result.exit,
            result.stdout,
            result.stderr + '\nHEAD changed during verification; rerun at the current HEAD.',
        )
    elapsed = int((time.monotonic() - started) * 1000)
    digest = hashlib.sha256((result.stdout + result.stderr).encode()).hexdigest()
    return Receipt(
        id=command.id,
        argv=command.argv,
        outcome=result.outcome,
        exit=result.exit,
        duration_ms=elapsed,
        stdout_tail=tail(result.stdout),
        stderr_tail=tail(result.stderr),
        digest=digest,
        head=head,
        phase=phase,
        at=now(),
    )


def append_receipt(paths: Paths, receipt: Receipt) -> None:
    paths.directory.mkdir(parents=True, exist_ok=True)
    with paths.receipts.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(asdict(receipt)) + '\n')


def load_receipts(paths: Paths) -> list[dict[str, object]]:
    if not paths.receipts.is_file():
        return []
    lines = paths.receipts.read_text(encoding='utf-8').splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def describe(receipt: Receipt) -> str:
    seconds = receipt.duration_ms / 1000
    line = f'{receipt.id} {receipt.outcome} exit={receipt.exit} {seconds:.1f}s\n'
    if receipt.outcome is Outcome.PASSED:
        return line
    detail = receipt.stderr_tail or receipt.stdout_tail
    return line + ''.join(f'  | {text}\n' for text in detail.splitlines())


def run_contract(options: argparse.Namespace, cwd: Path) -> tuple[str, bool]:
    paths = Paths(root=repository_root(cwd), slug=options.slug)
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        raise InvalidCommandError(0, 'stdin is not a JSON object') from error
    if not str(payload.get('approved_by', '')).strip():
        raise MissingApprovalError
    approval = Approval(by=payload['approved_by'], at=now(), head=resolve_head(paths.root))
    contract = load_contract(paths)
    added = merge(contract, list(payload.get('commands', [])), approval)
    save_contract(paths, contract)
    return f'contract: {len(contract.commands)} commands ({added} new)\n', True


def run_commands(options: argparse.Namespace, cwd: Path) -> tuple[str, bool]:
    paths = Paths(root=repository_root(cwd), slug=options.slug)
    if not paths.contract.is_file():
        raise NoContractError(paths.contract)
    contract = load_contract(paths)
    selected = sorted(contract.commands) if options.all else options.id
    unknown = [command_id for command_id in selected if command_id not in contract.commands]
    if unknown:
        raise UnknownCommandError(unknown)
    receipts = [
        receipt_for(contract.commands[command_id], paths, Phase(options.phase))
        for command_id in selected
    ]
    for receipt in receipts:
        append_receipt(paths, receipt)
    passed = all(receipt.outcome is Outcome.PASSED for receipt in receipts)
    return ''.join(describe(receipt) for receipt in receipts), passed


def state_of(command: Approved, latest: dict[str, object] | None, head: str | None) -> str:
    if latest is None:
        return 'never-run'
    if latest.get('head') != head:
        return f'stale ({latest["outcome"]} at {str(latest.get("head"))[:SHORT_SHA]})'
    return f'{latest["outcome"]} {latest.get("phase")} expect={command.expect_exit}'


def run_status(options: argparse.Namespace, cwd: Path) -> tuple[str, bool]:
    paths = Paths(root=repository_root(cwd), slug=options.slug)
    contract = load_contract(paths)
    latest = {str(receipt['id']): receipt for receipt in load_receipts(paths)}
    head = resolve_head(paths.root)
    rows = [
        f'{command_id} {state_of(command, latest.get(command_id), head)}\n'
        for command_id, command in sorted(contract.commands.items())
        if command_id.startswith(options.prefix)
    ]
    passing = all(row.split(' ', 2)[1] == 'pass' for row in rows)
    header = f'HEAD {(head or "unknown")[:SHORT_SHA]}\n'
    return header + (''.join(rows) or 'no matching commands\n'), passing


HANDLERS: dict[Command, Callable[[argparse.Namespace, Path], tuple[str, bool]]] = {
    Command.CONTRACT: run_contract,
    Command.RUN: run_commands,
    Command.STATUS: run_status,
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog='verification.py', description=__doc__.splitlines()[0])
    commands = root.add_subparsers(dest='command', required=True)
    contract = commands.add_parser(Command.CONTRACT, help='approve commands from stdin')
    contract.add_argument('--slug', required=True)
    run = commands.add_parser(Command.RUN, help='run approved commands by id')
    run.add_argument('--slug', required=True)
    chosen = run.add_mutually_exclusive_group(required=True)
    chosen.add_argument('--id', action='append')
    chosen.add_argument('--all', action='store_true', help='every approved command')
    run.add_argument('--phase', choices=[phase.value for phase in Phase], default='task')
    status = commands.add_parser(Command.STATUS, help='latest result per command')
    status.add_argument('--slug', required=True)
    status.add_argument('--prefix', default='')
    return root


def main(argv: list[str] | None = None) -> int:
    options = parser().parse_args(argv)
    try:
        output, passed = HANDLERS[Command(options.command)](options, Path.cwd())
    except VerificationError as error:
        sys.stderr.write(f'error: {error}\n')
        return EXIT_REJECTED
    sys.stdout.write(output)
    return 0 if passed else EXIT_FAILED


if __name__ == '__main__':
    raise SystemExit(main())
