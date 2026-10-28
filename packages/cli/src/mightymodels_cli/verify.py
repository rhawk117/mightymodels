"""The `mightymodels verify run` edge: arguments in, receipt lines out, an exit code back.

It opens the state as the server's lifespan does, builds the contract runner over the contract
service of one write unit, and renders each receipt the run recorded. A refusal (an invalid slug,
a missing data directory, a start outside a repository, git missing, a ticket without a contract)
goes to standard error as one line, and the exit code says refused instead of failed.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mightymodels_core.contract import ContractRunner, RunRequest
from mightymodels_core.edge import (
    SESSION_DATA_VARIABLE,
    create_clock,
    data_directory_from,
    open_state,
)
from mightymodels_core.primitives import StateError
from mightymodels_core.primitives.value_types import parse_slug
from mightymodels_core.process import get_process_runner
from mightymodels_core.units_of_work import TaskWork
from mightymodels_core.workspace import find_root

if TYPE_CHECKING:
    import argparse

    from mightymodels_core.contract import Receipt, RunResult
    from mightymodels_core.edge import OpenState

EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2
MILLISECONDS = 1000


def receipt_text(receipt: Receipt) -> str:
    seconds = receipt.duration_ms / MILLISECONDS
    line = f'{receipt.key} {receipt.outcome} exit={receipt.exit} {seconds:.1f}s\n'
    if receipt.outcome == 'pass':
        return line

    detail = receipt.stderr_tail or receipt.stdout_tail
    return line + ''.join(f'  | {text}\n' for text in detail.splitlines())


def result_text(result: RunResult) -> str:
    return ''.join(receipt_text(receipt) for receipt in result.receipts)


def refused(error: StateError) -> int:
    sys.stderr.write(f'error: {error}\n')
    return EXIT_REFUSED


async def run_in(state: OpenState, request: RunRequest) -> RunResult:
    work = TaskWork(
        database=state.database,
        repository_key=state.checkout.repository_key(),
        clock=create_clock(),
    )
    with work.write() as unit:
        runner = ContractRunner(
            service=unit.contracts,
            processes=get_process_runner(),
            git=state.git,
            clock=create_clock(),
            root=state.checkout.toplevel,
        )
        return await runner.run(request)


async def run_contracts(arguments: argparse.Namespace) -> int:
    slug = parse_slug(arguments.slug)
    if isinstance(slug, StateError):
        return refused(slug)

    asked = None if arguments.all else tuple(arguments.id)
    request = RunRequest(slug=slug, asked=asked, phase=arguments.phase)
    data_directory = data_directory_from(os.environ, SESSION_DATA_VARIABLE)
    start = find_root(os.environ, Path.cwd())
    try:
        async with open_state(data_directory, start) as state:
            result = await run_in(state, request)
    except StateError as error:
        return refused(error)

    sys.stdout.write(result_text(result))
    return EXIT_PASSED if result.is_passing else EXIT_FAILED


def verify_run(arguments: argparse.Namespace) -> int:
    return asyncio.run(run_contracts(arguments))
