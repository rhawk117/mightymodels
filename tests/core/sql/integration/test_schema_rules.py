from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import (
    MissingParentError,
    RejectedValueError,
    StatementFailedError,
)

from tests.core.sql.conftest import (
    CommandIdPart,
    CustomTicketPart,
    IdPart,
    InvestigationPart,
    KeyPart,
    LinkPart,
    NoPart,
    QueryPart,
    ReferencePart,
    SimilarityPart,
    SimilarityTextPart,
    TaskIdPart,
    TicketIdPart,
    TicketPart,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Database

    from tests.core.sql.conftest import Statements

pytestmark = pytest.mark.integration


@dataclass(slots=True, kw_only=True, frozen=True)
class Scene:
    database: Database
    statements: Statements
    repository_id: int
    ticket_id: int
    investigation_id: int


@pytest.fixture
def scene(database: Database, statements: Statements) -> Scene:
    with database.write() as unit:
        repository = unit.one(statements.add_repository, KeyPart(repository_key='owner/repo'))
        assert repository is not None
        ticket = unit.one(
            statements.add_ticket, TicketPart(repository_id=repository.id, slug='first')
        )
        assert ticket is not None
        investigation = unit.one(
            statements.add_investigation,
            InvestigationPart(repository_id=repository.id, investigation_key='probe'),
        )
        assert investigation is not None
    return Scene(
        database=database,
        statements=statements,
        repository_id=repository.id,
        ticket_id=ticket.id,
        investigation_id=investigation.id,
    )


def fill_ticket(scene: Scene) -> None:
    statements = scene.statements
    ticket = TicketIdPart(ticket_id=scene.ticket_id)
    with scene.database.write() as unit:
        task = unit.one(statements.add_task, ticket)
        command = unit.one(statements.add_command, ticket)
        assert task is not None
        assert command is not None
        unit.run(statements.add_attempt, TaskIdPart(task_id=task.id))
        unit.run(statements.add_receipt, CommandIdPart(contract_command_id=command.id))
        unit.run(statements.add_closing, ticket)
        unit.run(
            statements.link_investigation,
            LinkPart(ticket_id=scene.ticket_id, investigation_id=scene.investigation_id),
        )


class TestReferences:
    def test_an_orphan_insert_names_a_missing_parent(self, scene: Scene) -> None:
        orphan = TicketPart(repository_id=scene.repository_id + 1, slug='orphan')
        with pytest.raises(MissingParentError), scene.database.write() as unit:
            unit.one(scene.statements.add_ticket, orphan)

    def test_deleting_a_ticket_cascades_through_its_owned_rows(self, scene: Scene) -> None:
        fill_ticket(scene)
        with scene.database.write() as unit:
            unit.run(scene.statements.delete_ticket, IdPart(id=scene.ticket_id))
            counts = unit.one(scene.statements.count_owned, NoPart())
        assert counts is not None
        assert (
            counts.tasks,
            counts.attempts,
            counts.commands,
            counts.receipts,
            counts.links,
            counts.closings,
            counts.tickets,
        ) == (0, 0, 0, 0, 0, 0, 0)
        assert counts.investigations == 1

    def test_deleting_a_repository_is_refused(self, scene: Scene) -> None:
        with (
            pytest.raises(StatementFailedError, match='FOREIGN KEY'),
            scene.database.write() as unit,
        ):
            unit.run(scene.statements.delete_repository, IdPart(id=scene.repository_id))

    def test_deleting_a_linked_investigation_is_refused(self, scene: Scene) -> None:
        fill_ticket(scene)
        with (
            pytest.raises(StatementFailedError, match='FOREIGN KEY'),
            scene.database.write() as unit,
        ):
            unit.run(scene.statements.delete_investigation, IdPart(id=scene.investigation_id))

    def test_deleting_an_unlinked_investigation_succeeds(self, scene: Scene) -> None:
        with scene.database.write() as unit:
            deleted = unit.run(
                scene.statements.delete_investigation, IdPart(id=scene.investigation_id)
            )
        assert deleted == 1


def rejected_ticket_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'part',
        [
            pytest.param(CustomTicketPart(repository_id=1, models='{not json'), id='invalid-json'),
            pytest.param(CustomTicketPart(repository_id=1, status='archived'), id='unknown-enum'),
            pytest.param(CustomTicketPart(repository_id=1, plan_first=2), id='boolean-2'),
        ],
    )


class TestValues:
    @rejected_ticket_cases()
    def test_a_bad_value_is_rejected(self, scene: Scene, part: CustomTicketPart) -> None:
        with pytest.raises(RejectedValueError), scene.database.write() as unit:
            unit.run(scene.statements.add_custom_ticket, part)

    def test_a_good_value_is_accepted(self, scene: Scene) -> None:
        part = CustomTicketPart(repository_id=scene.repository_id, status='closed', plan_first=1)
        with scene.database.write() as unit:
            added = unit.run(scene.statements.add_custom_ticket, part)
        assert added == 1

    def test_timestamps_default_to_an_integer_epoch(self, scene: Scene) -> None:
        with scene.database.read() as unit:
            stamp = unit.one(scene.statements.ticket_stamp, IdPart(id=scene.ticket_id))
        assert stamp is not None
        assert stamp.storage == 'integer'
        assert stamp.validated_at > 0


class TestSimilarityIndex:
    def search(self, scene: Scene, query: str) -> list[str]:
        with scene.database.read() as unit:
            rows = unit.all(scene.statements.search_similarity, QueryPart(query=query))
        return [row.reference for row in rows]

    def test_the_index_follows_insert_update_and_delete(self, scene: Scene) -> None:
        statements = scene.statements
        added = SimilarityPart(
            repository_id=scene.repository_id, reference='e1', text='retry the webhook'
        )
        with scene.database.write() as unit:
            unit.run(statements.add_similarity, added)
        assert self.search(scene, 'webhook') == ['e1']

        with scene.database.write() as unit:
            unit.run(
                statements.update_similarity,
                SimilarityTextPart(reference='e1', text='drain the queue'),
            )
        assert self.search(scene, 'webhook') == []
        assert self.search(scene, 'queue') == ['e1']

        with scene.database.write() as unit:
            unit.run(statements.delete_similarity, ReferencePart(reference='e1'))
        assert self.search(scene, 'queue') == []
