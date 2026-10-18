"""The approved contract commands of a ticket and the receipts recorded against them."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from msgspec import Struct

from mightymodels_core.database import Command, Query

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration


class Outcome(StrEnum):
    PASSED = 'pass'
    FAIL = 'fail'
    TIMEOUT = 'timeout'
    NOT_FOUND = 'not-found'
    REFUSED = 'refused'
    UNDECODABLE = 'undecodable'


class Phase(StrEnum):
    PLANNING = 'planning'
    TASK = 'task'
    REVIEW = 'review'
    LANDING = 'landing'


class ApproveContractCommandParams(Struct, frozen=True, kw_only=True):
    ticket_id: int
    command_key: str
    task_key: str | None
    argv: list[str]
    expect_exit: int
    timeout: int
    approved_by: str
    approved_at: datetime
    head: str | None


class ContractCommandsParams(Struct, frozen=True, kw_only=True, gc=False):
    ticket_id: int
    limit: int


class ContractCommandCountParams(Struct, frozen=True, kw_only=True, gc=False):
    ticket_id: int


class RecordReceiptParams(Struct, frozen=True, kw_only=True):
    contract_command_id: int
    argv: list[str]
    outcome: Outcome
    exit: int | None
    duration_ms: int
    stdout_tail: str
    stderr_tail: str
    digest: str
    head: str | None
    phase: Phase
    at: datetime


class ContractCommandRow(Struct, frozen=True, kw_only=True):
    id: int
    command_key: str
    task_key: str | None
    argv: list[str]
    expect_exit: int
    timeout: int
    approved_by: str
    approved_at: datetime
    head: str | None


class ContractCommandCountRow(Struct, frozen=True, kw_only=True, gc=False):
    count: int


class ReceiptRow(Struct, frozen=True, kw_only=True):
    command_key: str
    argv: list[str]
    outcome: Outcome
    exit: int | None
    duration_ms: int
    stdout_tail: str
    stderr_tail: str
    digest: str
    head: str | None
    phase: Phase
    at: datetime


APPROVE_CONTRACT_COMMAND = Command(
    name='approve_contract_command', params=ApproveContractCommandParams
)
CONTRACT_COMMANDS_OF_TICKET = Query(
    name='contract_commands_of_ticket', params=ContractCommandsParams, row=ContractCommandRow
)
CONTRACT_COMMAND_COUNT = Query(
    name='contract_command_count', params=ContractCommandCountParams, row=ContractCommandCountRow
)
RECORD_RECEIPT = Command(name='record_receipt', params=RecordReceiptParams)
LATEST_RECEIPTS = Query(name='latest_receipts', params=ContractCommandsParams, row=ReceiptRow)

DECLARATIONS: tuple[Declaration, ...] = (
    APPROVE_CONTRACT_COMMAND,
    CONTRACT_COMMANDS_OF_TICKET,
    CONTRACT_COMMAND_COUNT,
    RECORD_RECEIPT,
    LATEST_RECEIPTS,
)
