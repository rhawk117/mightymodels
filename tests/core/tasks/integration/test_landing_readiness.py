"""Landing readiness over real sqlite: a live L* command, every live command passing at HEAD."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract import (
    ContractService,
    RetireRequest,
    SqliteContractRepository,
)
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.tasks import SqliteAttemptRepository, SqliteTaskRepository, TaskReadService
from mightymodels_core.tasks.gates import NO_LANDING_COMMAND
from mightymodels_core.tickets import SqliteTicketRepository

from tests.core.contract.contract_builders import (
    HEAD,
    SERVICE_MOMENT,
    create_command,
    create_receipt,
)
from tests.core.primitives.clock import create_fake_clock
from tests.core.tasks.repository_builders import TICKET_SLUGS

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database
    from mightymodels_core.vocabulary.contract import Phase

SLUG = TICKET_SLUGS[0]
LANDING = 'L1'
INTEGRATION = 'I1'
NO_PLAN_TASK = 'no plan task has been started'


@dataclass(slots=True, kw_only=True, frozen=True)
class LandingHarness:
    service: ContractService
    reads: TaskReadService

    def problems(self, head: str = HEAD) -> list[str]:
        return [
            problem for problem in self.reads.ready(SLUG, head).problems if problem != NO_PLAN_TASK
        ]

    def approve(self, *keys: str) -> None:
        self.service.approve(SLUG, [create_command(key) for key in keys], head=HEAD)

    def pass_at(self, key: str, head: str, phase: Phase = 'landing') -> None:
        receipt = replace(create_receipt(key), head=head, phase=phase)
        self.service.record(SLUG, [receipt])

    def retire(self, key: str) -> None:
        self.service.retire(
            SLUG, RetireRequest(key=key, by='planner', why='dropped', approval_source='fallback')
        )


@pytest.fixture
def harness(database: Database, staged_ticket_ids: tuple[int, int]) -> Generator[LandingHarness]:
    del staged_ticket_ids
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        tickets = SqliteTicketRepository(unit=unit, repository_id=repository.id)
        contracts = SqliteContractRepository(unit=unit)
        yield LandingHarness(
            service=ContractService(
                tickets=tickets, contracts=contracts, clock=create_fake_clock(SERVICE_MOMENT)
            ),
            reads=TaskReadService(
                tickets=tickets,
                tasks=SqliteTaskRepository(unit=unit),
                attempts=SqliteAttemptRepository(unit=unit),
                contracts=contracts,
            ),
        )


class TestLandingReadiness:
    def test_a_contract_with_no_command_is_refused(self, harness: LandingHarness) -> None:
        assert harness.problems() == [NO_LANDING_COMMAND]

    def test_a_contract_with_only_an_integration_command_is_refused(
        self, harness: LandingHarness
    ) -> None:
        harness.approve(INTEGRATION)
        harness.pass_at(INTEGRATION, HEAD)

        assert harness.problems() == [NO_LANDING_COMMAND]

    def test_a_contract_with_only_retired_commands_is_refused(
        self, harness: LandingHarness
    ) -> None:
        harness.approve(LANDING)
        harness.pass_at(LANDING, HEAD)
        harness.retire(LANDING)

        assert harness.problems() == [NO_LANDING_COMMAND]

    @pytest.mark.parametrize('phase', ['task', 'landing'])
    def test_a_pass_at_head_counts_in_any_phase(
        self, harness: LandingHarness, phase: Phase
    ) -> None:
        harness.approve(LANDING)
        harness.pass_at(LANDING, HEAD, phase)

        assert harness.problems() == []

    def test_a_receipt_at_an_older_head_is_refused(self, harness: LandingHarness) -> None:
        harness.approve(LANDING)
        harness.pass_at(LANDING, HEAD)

        assert harness.problems('newer01') == [f'{LANDING} has no receipt at the current HEAD']

    def test_a_failed_receipt_is_refused(self, harness: LandingHarness) -> None:
        harness.approve(LANDING)
        harness.service.record(SLUG, [create_receipt(LANDING, 'fail')])

        assert harness.problems() == [f'{LANDING} fail at HEAD']

    def test_a_retired_command_is_ignored(self, harness: LandingHarness) -> None:
        harness.approve(LANDING, INTEGRATION)
        harness.pass_at(LANDING, HEAD)
        harness.retire(INTEGRATION)

        assert harness.problems() == []

    def test_a_live_integration_command_must_pass_too(self, harness: LandingHarness) -> None:
        harness.approve(LANDING, INTEGRATION)
        harness.pass_at(LANDING, HEAD)

        assert harness.problems() == [f'{INTEGRATION} has no receipt at the current HEAD']
