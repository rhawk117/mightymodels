"""A ticket's approved commands and their receipts, reached only through a repository.

`contract_transaction` opens a transaction on the database and hands out the repository, which
holds that transaction's session, so the contract service never sees a session. A domain that reads
commands or receipts inside its own transaction builds a `ContractRepository` on that transaction's
session.
"""

import re
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from mightymodels_plugin.database import Database
from mightymodels_plugin.slug import Slug
from mightymodels_plugin.task_id import TASK_ID_PATTERN
from mightymodels_plugin.tools.contract.schema import ContractCommand, Receipt
from mightymodels_plugin.tools.contract.tables import CommandRow, ReceiptRow

TASK_ID = re.compile(TASK_ID_PATTERN)


@dataclass(slots=True, kw_only=True, frozen=True)
class Approval:
    at: str
    head: str | None


def owning_task(command_id: str) -> str | None:
    task_id, separator, _ = command_id.partition('.')
    return task_id if separator and TASK_ID.match(task_id) else None


def command_row(slug: Slug, command: ContractCommand, approval: Approval) -> CommandRow:
    return CommandRow(
        slug=slug.root,
        command_id=command.id,
        task_id=owning_task(command.id),
        argv=list(command.argv),
        expect_exit=command.expect_exit,
        timeout=command.timeout,
        approved_by=command.approved_by,
        approved_at=approval.at,
        head=approval.head,
    )


def receipt_row(slug: Slug, receipt: Receipt) -> ReceiptRow:
    return ReceiptRow(
        slug=slug.root,
        command_id=receipt.id,
        argv=list(receipt.argv),
        outcome=receipt.outcome,
        exit=receipt.exit,
        duration_ms=receipt.duration_ms,
        stdout_tail=receipt.stdout_tail,
        stderr_tail=receipt.stderr_tail,
        digest=receipt.digest,
        head=receipt.head,
        phase=receipt.phase,
        at=receipt.at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractRepository:
    session: Session

    def commands(self, slug: Slug) -> list[CommandRow]:
        query = (
            select(CommandRow).where(CommandRow.slug == slug.root).order_by(CommandRow.command_id)
        )
        return list(self.session.scalars(query))

    def latest_receipts(self, slug: Slug) -> dict[str, ReceiptRow]:
        query = select(ReceiptRow).where(ReceiptRow.slug == slug.root).order_by(ReceiptRow.id)
        return {receipt.command_id: receipt for receipt in self.session.scalars(query)}

    def approve(self, slug: Slug, commands: Iterable[ContractCommand], approval: Approval) -> None:
        self.session.add_all(command_row(slug, command, approval) for command in commands)

    def record(self, slug: Slug, receipts: Iterable[Receipt]) -> None:
        self.session.add_all(receipt_row(slug, receipt) for receipt in receipts)


@contextmanager
def contract_transaction(database: Database) -> Generator[ContractRepository]:
    with database.transaction() as session:
        yield ContractRepository(session=session)
