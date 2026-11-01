"""The contract pick policy: which approved commands a run picks and which asks it refuses."""

from dataclasses import replace
from datetime import UTC, datetime

from mightymodels_core.contract import (
    NoContractError,
    PickPolicy,
    RecordedCommand,
    RetiredPickError,
    UnknownCommandError,
)
from mightymodels_core.contract.records import Retirement
from mightymodels_core.primitives import Slug

from tests.core.contract.contract_builders import FIRST_KEY, SECOND_KEY

SLUG = Slug('policy-subject')


def recorded(key: str, argv: tuple[str, ...] = ('make', 'test')) -> RecordedCommand:
    return RecordedCommand(key=key, argv=argv, expect_exit=0, timeout=300)


class TestPickPolicy:
    held = (recorded(SECOND_KEY), recorded(FIRST_KEY))

    def test_a_ticket_with_no_commands_has_no_contract(self) -> None:
        problem = PickPolicy(slug=SLUG, held=(), asked=None).get_pick_problem()

        assert isinstance(problem, NoContractError)
        assert problem.slug == SLUG

    def test_ids_outside_the_contract_are_unknown(self) -> None:
        asked = [FIRST_KEY, 'I10', 'I8']

        problem = PickPolicy(slug=SLUG, held=self.held, asked=asked).get_pick_problem()

        assert isinstance(problem, UnknownCommandError)
        assert problem.unknown == ('I10', 'I8')

    def test_a_retired_id_asked_is_refused_as_retired(self) -> None:
        retirement = Retirement(
            by='planner', why='dropped', approval_source='fallback', at=datetime.now(tz=UTC)
        )
        retired = replace(recorded(FIRST_KEY), retirement=retirement)
        held = (retired, recorded(SECOND_KEY))

        problem = PickPolicy(slug=SLUG, held=held, asked=[FIRST_KEY, 'I10']).get_pick_problem()

        assert isinstance(problem, RetiredPickError)
        assert problem.retired == (FIRST_KEY,)

    def test_no_ids_picks_every_command_in_approval_order(self) -> None:
        policy = PickPolicy(slug=SLUG, held=self.held, asked=None)

        assert policy.get_pick_problem() is None
        assert [command.key for command in policy.picked_commands] == [SECOND_KEY, FIRST_KEY]

    def test_no_ids_picks_i2_before_i10(self) -> None:
        held = (recorded('I2'), recorded('I10'), recorded('I1'))

        policy = PickPolicy(slug=SLUG, held=held, asked=None)

        assert [command.key for command in policy.picked_commands] == ['I2', 'I10', 'I1']

    def test_asked_ids_pick_in_the_order_asked(self) -> None:
        policy = PickPolicy(slug=SLUG, held=self.held, asked=[SECOND_KEY, FIRST_KEY])

        assert policy.get_pick_problem() is None
        assert [command.key for command in policy.picked_commands] == [SECOND_KEY, FIRST_KEY]
