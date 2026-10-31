"""Approval accepts only the command ids that start with I or L and end in digits."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract import ApprovalPolicy, InvalidCommandKeyError

from tests.core.contract.contract_builders import create_command

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet


@dataclass(slots=True, kw_only=True, frozen=True)
class IdScenario:
    key: str
    accepted: bool

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.key or 'empty')


def command_id_cases() -> pytest.MarkDecorator:
    accepted = ['I1', 'L1', 'I10']
    refused = ['T1.AC-1', 'T1', 'R1', 'C1.ci', 'lint', 'i1', 'I', 'L', 'IL1', 'I1.AC-1', 'I-1']
    scenarios = [IdScenario(key=key, accepted=True) for key in accepted] + [
        IdScenario(key=key, accepted=False) for key in refused
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


@command_id_cases()
def test_approval_accepts_only_i_and_l_ids(scenario: IdScenario) -> None:
    policy = ApprovalPolicy(commands=[create_command(scenario.key)], held=[])

    problem = policy.get_approval_problem()

    assert type(problem) is (type(None) if scenario.accepted else InvalidCommandKeyError)
