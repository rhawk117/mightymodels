from types import MappingProxyType
from typing import Any

import pytest
from mightymodels_mcp.contract.schemas import (
    USER_APPROVER,
    ContractApproveRequest,
    leaves_approver_blank,
)
from mightymodels_mcp.contract.schemas import create_approved_commands as approved_commands_of
from mightymodels_mcp.server.requests import NAME_LIMIT
from pydantic import ValidationError

COMMAND = MappingProxyType({'id': 'T1.check', 'argv': ('uv', 'run', 'pytest')})
APPROVE = MappingProxyType({'slug': 'probe-ticket', 'commands': (COMMAND,)})


def create_approve(**given: Any) -> ContractApproveRequest:
    return ContractApproveRequest.model_validate({**APPROVE, **given})


def create_commands(*given: dict[str, Any]) -> ContractApproveRequest:
    return create_approve(commands=tuple({**COMMAND, **command} for command in given))


def invalid_approve_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'change',
        [
            pytest.param({'slug': 'Not A Slug'}, id='slug'),
            pytest.param({'unknown': 'field'}, id='extra-field'),
            pytest.param({'commands': ({'id': 'T1.check'},)}, id='no-argv'),
            pytest.param({'commands': ({**COMMAND, 'argv': 'pytest'},)}, id='argv-string'),
            pytest.param({'commands': ({**COMMAND, 'expect_exit': 'zero'},)}, id='expect-exit'),
            pytest.param(
                {'commands': ({**COMMAND, 'approved_by': 'x' * (NAME_LIMIT + 1)},)}, id='approver'
            ),
        ],
    )


class TestContractApproveRequest:
    @invalid_approve_cases()
    def test_invalid_request_is_refused(self, change: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            create_approve(**change)

    def test_command_defaults_to_exit_zero_five_minutes_and_no_approver(self) -> None:
        command = create_approve().commands[0]

        assert (command.expect_exit, command.timeout, command.approved_by) == (0, 300, '')

    def test_command_argv_is_kept_as_given(self) -> None:
        assert create_approve().commands[0].argv == ('uv', 'run', 'pytest')


class TestLeavesApproverBlank:
    def test_unnamed_approver_is_blank(self) -> None:
        assert leaves_approver_blank(create_commands({}))

    def test_whitespace_approver_is_blank(self) -> None:
        assert leaves_approver_blank(create_commands({'approved_by': ' '}))

    def test_one_blank_among_named_is_blank(self) -> None:
        assert leaves_approver_blank(create_commands({'approved_by': 'lead'}, {'id': 'T1.lint'}))

    def test_every_command_named_is_not_blank(self) -> None:
        assert not leaves_approver_blank(create_commands({'approved_by': 'lead'}))


class TestCreateApprovedCommands:
    def test_blank_approver_takes_the_fallback(self) -> None:
        request = create_commands({'expect_exit': 1, 'timeout': 60})

        (approved,) = approved_commands_of(request, USER_APPROVER)

        assert (approved.key, approved.argv, approved.expect_exit, approved.timeout) == (
            'T1.check',
            ('uv', 'run', 'pytest'),
            1,
            60,
        )
        assert approved.approved_by == USER_APPROVER

    def test_named_approver_is_kept(self) -> None:
        (approved,) = approved_commands_of(create_commands({'approved_by': 'lead'}), USER_APPROVER)

        assert approved.approved_by == 'lead'
