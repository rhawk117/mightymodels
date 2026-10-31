"""Retiring a contract command over real sqlite: the gates stop counting it, the row stays."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract import (
    AlreadyRetiredError,
    ChangedCommandError,
    ContractService,
    RetiredCommandError,
    RetireRequest,
    SqliteContractRepository,
    UnknownCommandError,
)
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.tasks import SqliteAttemptRepository, SqliteTaskRepository, TaskReadService
from mightymodels_core.tickets import SqliteTicketRepository

from tests.core.contract.contract_builders import (
    FIRST_KEY,
    HEAD,
    SECOND_KEY,
    SERVICE_MOMENT,
    TICKET_SLUGS,
    create_command,
    create_receipt,
)
from tests.core.primitives.clock import create_fake_clock

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database

SLUG = TICKET_SLUGS[0]
CHANGED_ARGV = ('make', 'lint')


def create_request(key: str) -> RetireRequest:
    return RetireRequest(key=key, by='planner', why='no longer applies', approval_source='fallback')


@dataclass(slots=True, kw_only=True, frozen=True)
class RetireHarness:
    service: ContractService
    reads: TaskReadService
    contracts: SqliteContractRepository
    ticket_id: int


@pytest.fixture
def harness(database: Database, staged_ticket_ids: tuple[int, int]) -> Generator[RetireHarness]:
    ticket_id, _ = staged_ticket_ids
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        tickets = SqliteTicketRepository(unit=unit, repository_id=repository.id)
        contracts = SqliteContractRepository(unit=unit)
        yield RetireHarness(
            service=ContractService(
                tickets=tickets, contracts=contracts, clock=create_fake_clock(SERVICE_MOMENT)
            ),
            reads=TaskReadService(
                tickets=tickets,
                tasks=SqliteTaskRepository(unit=unit),
                attempts=SqliteAttemptRepository(unit=unit),
                contracts=contracts,
            ),
            contracts=contracts,
            ticket_id=ticket_id,
        )


@pytest.fixture
def approved(harness: RetireHarness) -> RetireHarness:
    harness.service.approve(
        SLUG, [create_command(FIRST_KEY), create_command(SECOND_KEY)], head=HEAD
    )
    return harness


class TestRetire:
    def test_readiness_no_longer_names_a_retired_command_without_a_receipt(
        self, approved: RetireHarness
    ) -> None:
        before = approved.reads.ready(SLUG, HEAD).problems
        approved.service.retire(SLUG, create_request(FIRST_KEY))
        after = approved.reads.ready(SLUG, HEAD).problems

        assert any(FIRST_KEY in problem for problem in before)
        assert not any(FIRST_KEY in problem for problem in after)
        assert any(SECOND_KEY in problem for problem in after)

    def test_status_lists_the_retired_command_apart_from_the_live_ones(
        self, approved: RetireHarness
    ) -> None:
        approved.service.retire(SLUG, create_request(FIRST_KEY))

        status = approved.service.status(SLUG, HEAD)

        assert [entry.command.key for entry in status.commands] == [SECOND_KEY]
        assert [command.key for command in status.retired] == [FIRST_KEY]
        retirement = status.retired[0].retirement
        assert retirement is not None
        assert (retirement.by, retirement.at) == ('planner', SERVICE_MOMENT)

    def test_pick_without_ids_skips_the_retired_command(self, approved: RetireHarness) -> None:
        approved.service.retire(SLUG, create_request(FIRST_KEY))

        picked = approved.service.pick(SLUG, None)

        assert [command.key for command in picked] == [SECOND_KEY]

    def test_pick_by_name_refuses_the_retired_command(self, approved: RetireHarness) -> None:
        approved.service.retire(SLUG, create_request(FIRST_KEY))

        with pytest.raises(UnknownCommandError):
            approved.service.pick(SLUG, [FIRST_KEY])

    def test_the_row_and_its_receipts_survive(self, approved: RetireHarness) -> None:
        approved.service.record(SLUG, [create_receipt(FIRST_KEY)])

        approved.service.retire(SLUG, create_request(FIRST_KEY))

        keys = [command.key for command in approved.contracts.commands(approved.ticket_id)]
        assert keys == [FIRST_KEY, SECOND_KEY]
        assert FIRST_KEY in approved.contracts.latest_receipts(approved.ticket_id)


class TestRetireRefusals:
    def test_retiring_an_unknown_id_is_refused(self, approved: RetireHarness) -> None:
        with pytest.raises(UnknownCommandError):
            approved.service.retire(SLUG, create_request('I9'))

    def test_retiring_a_retired_id_is_refused(self, approved: RetireHarness) -> None:
        approved.service.retire(SLUG, create_request(FIRST_KEY))

        with pytest.raises(AlreadyRetiredError):
            approved.service.retire(SLUG, create_request(FIRST_KEY))


class TestReplaceCommand:
    def test_an_approved_id_still_refuses_a_changed_argv(self, approved: RetireHarness) -> None:
        with pytest.raises(ChangedCommandError):
            approved.service.approve(
                SLUG, [create_command(FIRST_KEY, argv=CHANGED_ARGV)], head=HEAD
            )

    def test_replacing_a_command_approves_a_new_id_and_retires_the_old(
        self, approved: RetireHarness
    ) -> None:
        approved.service.approve(SLUG, [create_command('I3', argv=CHANGED_ARGV)], head=HEAD)
        approved.service.retire(SLUG, create_request(FIRST_KEY))

        status = approved.service.status(SLUG, HEAD)

        assert [entry.command.key for entry in status.commands] == [SECOND_KEY, 'I3']
        assert [command.key for command in status.retired] == [FIRST_KEY]

    def test_approving_a_retired_id_again_is_refused_naming_the_id(
        self, approved: RetireHarness
    ) -> None:
        approved.service.retire(SLUG, create_request(FIRST_KEY))

        with pytest.raises(RetiredCommandError, match=r'I1.*approve a new id'):
            approved.service.approve(SLUG, [create_command(FIRST_KEY)], head=HEAD)

    def test_a_retired_id_gets_the_retired_message_even_with_a_changed_argv(
        self, approved: RetireHarness
    ) -> None:
        approved.service.retire(SLUG, create_request(FIRST_KEY))

        with pytest.raises(RetiredCommandError):
            approved.service.approve(
                SLUG, [create_command(FIRST_KEY, argv=CHANGED_ARGV)], head=HEAD
            )
