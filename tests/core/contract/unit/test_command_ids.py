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
    name: str
    key: str
    accepted: bool
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


def command_id_cases() -> pytest.MarkDecorator:
    accepted = ['I1', 'L1', 'I10']
    refused = ['T1.AC-1', 'T1', 'R1', 'C1.ci', 'lint', 'i1', 'I', 'L', 'IL1', 'I1.AC-1', 'I-1']
    scenarios = [IdScenario(name=key, key=key, accepted=True) for key in accepted] + [
        IdScenario(name=key, key=key, accepted=False) for key in refused
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


class TestApprovalCommandIds:
    def find_problem(self, scenario: IdScenario) -> object | None:
        policy = ApprovalPolicy(commands=[create_command(scenario.key)], held=[])
        return policy.get_approval_problem()

    @command_id_cases()
    def test_approval_accepts_only_i_and_l_ids(self, scenario: IdScenario) -> None:
        problem = self.find_problem(scenario)

        assert type(problem) is (type(None) if scenario.accepted else InvalidCommandKeyError)
