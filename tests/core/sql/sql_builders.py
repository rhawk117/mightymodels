"""Test-local statements, Structs and script helpers for the schema tests."""

import re
from dataclasses import dataclass
from importlib.resources import files
from typing import TYPE_CHECKING

from mightymodels_core.database import Command, Query
from msgspec import Struct

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration

SCHEMA = files('mightymodels_core.sql').joinpath('schema.sql')

STATEMENTS = """
-- name: add_repository
INSERT INTO repositories (repository_key) VALUES (:repository_key)
RETURNING json_object('id', id);

-- name: add_ticket
INSERT INTO tickets (
  repository_id, slug, ticket, summary, branch, scope, plan_first, models, context
)
VALUES (:repository_id, :slug, :slug, 'summary', 'main', 'sm', 0, '{}', '[]')
RETURNING json_object('id', id);

-- name: add_custom_ticket
INSERT INTO tickets (
  repository_id, slug, ticket, summary, branch, status, scope, plan_first, models, context
)
VALUES (
  :repository_id, 'custom', 'custom', 'summary', 'main', :status, 'sm', :plan_first, :models, '[]'
);

-- name: add_investigation
INSERT INTO investigations (repository_id, investigation_key, target, kind)
VALUES (:repository_id, :investigation_key, 'target', 'known')
RETURNING json_object('id', id);

-- name: link_investigation
INSERT INTO ticket_investigations (ticket_id, investigation_id)
VALUES (:ticket_id, :investigation_id);

-- name: add_task
INSERT INTO tasks (ticket_id, task_key, status, owned) VALUES (:ticket_id, 'T1', 'pending', '[]')
RETURNING json_object('id', id);

-- name: add_attempt
INSERT INTO task_attempts (task_id, worker) VALUES (:task_id, 'engineer');

-- name: add_command
INSERT INTO contract_commands (ticket_id, command_key, argv, approved_by)
VALUES (:ticket_id, 'T1.AC-1', '["true"]', 'user')
RETURNING json_object('id', id);

-- name: add_receipt
INSERT INTO receipts (
  contract_command_id, argv, outcome, duration_ms, stdout_tail, stderr_tail, digest, phase
)
VALUES (:contract_command_id, '["true"]', 'pass', 1, '', '', 'abc', 'task');

-- name: add_closing
INSERT INTO closings (ticket_id, shipped, archive) VALUES (:ticket_id, 'done', 'archive.md');

-- name: count_owned
SELECT json_object(
  'tasks', (SELECT count(*) FROM tasks),
  'attempts', (SELECT count(*) FROM task_attempts),
  'commands', (SELECT count(*) FROM contract_commands),
  'receipts', (SELECT count(*) FROM receipts),
  'links', (SELECT count(*) FROM ticket_investigations),
  'closings', (SELECT count(*) FROM closings),
  'tickets', (SELECT count(*) FROM tickets),
  'investigations', (SELECT count(*) FROM investigations)
);

-- name: delete_ticket
DELETE FROM tickets WHERE id = :id;

-- name: delete_repository
DELETE FROM repositories WHERE id = :id;

-- name: delete_investigation
DELETE FROM investigations WHERE id = :id;

-- name: ticket_stamp
SELECT json_object('validated_at', validated_at, 'storage', typeof(validated_at))
FROM tickets WHERE id = :id;

-- name: add_similarity
INSERT INTO similarity (repository_id, kind, reference, text)
VALUES (:repository_id, 'ledger-entry', :reference, :text);

-- name: update_similarity
UPDATE similarity SET text = :text WHERE reference = :reference;

-- name: delete_similarity
DELETE FROM similarity WHERE reference = :reference;

-- name: search_similarity
SELECT json_object('reference', s.reference)
FROM similarity_index AS i JOIN similarity AS s ON s.id = i.rowid
WHERE similarity_index MATCH :query
ORDER BY s.id;
"""


class KeyPart(Struct, frozen=True, kw_only=True):
    repository_key: str


class IdPart(Struct, frozen=True, kw_only=True):
    id: int


class IdRow(Struct, frozen=True, kw_only=True):
    id: int


class TicketPart(Struct, frozen=True, kw_only=True):
    repository_id: int
    slug: str


class CustomTicketPart(Struct, frozen=True, kw_only=True):
    repository_id: int
    status: str = 'staged'
    plan_first: int = 0
    models: str = '{}'


class InvestigationPart(Struct, frozen=True, kw_only=True):
    repository_id: int
    investigation_key: str


class LinkPart(Struct, frozen=True, kw_only=True):
    ticket_id: int
    investigation_id: int


class TicketIdPart(Struct, frozen=True, kw_only=True):
    ticket_id: int


class TaskIdPart(Struct, frozen=True, kw_only=True):
    task_id: int


class CommandIdPart(Struct, frozen=True, kw_only=True):
    contract_command_id: int


class OwnedCounts(Struct, frozen=True, kw_only=True):
    tasks: int
    attempts: int
    commands: int
    receipts: int
    links: int
    closings: int
    tickets: int
    investigations: int


class StampRow(Struct, frozen=True, kw_only=True):
    validated_at: int
    storage: str


class SimilarityPart(Struct, frozen=True, kw_only=True):
    repository_id: int
    reference: str
    text: str


class SimilarityTextPart(Struct, frozen=True, kw_only=True):
    reference: str
    text: str


class ReferencePart(Struct, frozen=True, kw_only=True):
    reference: str


class QueryPart(Struct, frozen=True, kw_only=True):
    query: str


class ReferenceRow(Struct, frozen=True, kw_only=True):
    reference: str


class NoPart(Struct, frozen=True, kw_only=True):
    pass


@dataclass(slots=True, kw_only=True, frozen=True)
class Statements:
    add_repository: Query[KeyPart, IdRow]
    add_ticket: Query[TicketPart, IdRow]
    add_custom_ticket: Command[CustomTicketPart]
    add_investigation: Query[InvestigationPart, IdRow]
    link_investigation: Command[LinkPart]
    add_task: Query[TicketIdPart, IdRow]
    add_attempt: Command[TaskIdPart]
    add_command: Query[TicketIdPart, IdRow]
    add_receipt: Command[CommandIdPart]
    add_closing: Command[TicketIdPart]
    count_owned: Query[NoPart, OwnedCounts]
    delete_ticket: Command[IdPart]
    delete_repository: Command[IdPart]
    delete_investigation: Command[IdPart]
    ticket_stamp: Query[IdPart, StampRow]
    add_similarity: Command[SimilarityPart]
    update_similarity: Command[SimilarityTextPart]
    delete_similarity: Command[ReferencePart]
    search_similarity: Query[QueryPart, ReferenceRow]

    @property
    def declarations(self) -> tuple[Declaration, ...]:
        return (
            self.add_repository,
            self.add_ticket,
            self.add_custom_ticket,
            self.add_investigation,
            self.link_investigation,
            self.add_task,
            self.add_attempt,
            self.add_command,
            self.add_receipt,
            self.add_closing,
            self.count_owned,
            self.delete_ticket,
            self.delete_repository,
            self.delete_investigation,
            self.ticket_stamp,
            self.add_similarity,
            self.update_similarity,
            self.delete_similarity,
            self.search_similarity,
        )


def create_statements() -> Statements:
    return Statements(
        add_repository=Query(name='add_repository', params=KeyPart, row=IdRow),
        add_ticket=Query(name='add_ticket', params=TicketPart, row=IdRow),
        add_custom_ticket=Command(name='add_custom_ticket', params=CustomTicketPart),
        add_investigation=Query(name='add_investigation', params=InvestigationPart, row=IdRow),
        link_investigation=Command(name='link_investigation', params=LinkPart),
        add_task=Query(name='add_task', params=TicketIdPart, row=IdRow),
        add_attempt=Command(name='add_attempt', params=TaskIdPart),
        add_command=Query(name='add_command', params=TicketIdPart, row=IdRow),
        add_receipt=Command(name='add_receipt', params=CommandIdPart),
        add_closing=Command(name='add_closing', params=TicketIdPart),
        count_owned=Query(name='count_owned', params=NoPart, row=OwnedCounts),
        delete_ticket=Command(name='delete_ticket', params=IdPart),
        delete_repository=Command(name='delete_repository', params=IdPart),
        delete_investigation=Command(name='delete_investigation', params=IdPart),
        ticket_stamp=Query(name='ticket_stamp', params=IdPart, row=StampRow),
        add_similarity=Command(name='add_similarity', params=SimilarityPart),
        update_similarity=Command(name='update_similarity', params=SimilarityTextPart),
        delete_similarity=Command(name='delete_similarity', params=ReferencePart),
        search_similarity=Query(name='search_similarity', params=QueryPart, row=ReferenceRow),
    )


def strip_comments(script: str) -> str:
    return re.sub(r'--[^\n]*', '', script)
