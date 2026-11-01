import re

import pytest
from mightymodels_hooks.branch_state import Landing
from mightymodels_hooks.main_thread import (
    CONTRACT_APPROVE_TOOL,
    CONTRACT_RETIRE_TOOL,
    CONTRACT_RUN_TOOL,
)
from mightymodels_hooks.payloads import PreToolUsePayload

from tests.hooks.dispatch.dispatch_builders import SLUG
from tests.hooks.main_thread.main_thread_builders import (
    PUSH,
    WORKER,
    FakeTicketOnBranch,
    bash_payload,
    judge,
)
from tests.hooks.registration.registration_builders import read_registered_hooks


def contract_payload(
    agent_id: str | None, agent_type: str | None = None, tool: str = CONTRACT_RUN_TOOL
) -> PreToolUsePayload:
    return PreToolUsePayload(
        tool_name=tool, tool_input={}, agent_id=agent_id, agent_type=agent_type
    )


def primary_only_tool_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'tool',
        [
            pytest.param(CONTRACT_RUN_TOOL, id='run'),
            pytest.param(CONTRACT_APPROVE_TOOL, id='approve'),
            pytest.param(CONTRACT_RETIRE_TOOL, id='retire'),
        ],
    )


def subagent_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('agent_type', [None, WORKER])


class TestContractRunDenial:
    @primary_only_tool_cases()
    @subagent_cases()
    async def test_a_subagent_is_denied(self, agent_type: str | None, tool: str) -> None:
        fake = FakeTicketOnBranch()
        verdict = await judge(contract_payload('agent-1', agent_type, tool), fake)
        assert (verdict.decision, fake.reads) == ('deny', [])

    @primary_only_tool_cases()
    async def test_the_primary_passes_without_a_read(self, tool: str) -> None:
        fake = FakeTicketOnBranch()
        verdict = await judge(contract_payload(None, tool=tool), fake)
        assert (verdict.decision, fake.reads) == (None, [])

    async def test_another_mcp_tool_from_a_subagent_passes(self) -> None:
        payload = PreToolUsePayload(
            tool_name='mcp__plugin_mightymodels_mighty-mcp__task_start',
            tool_input={},
            agent_id='agent-1',
        )
        verdict = await judge(payload, FakeTicketOnBranch())
        assert verdict.decision is None

    async def test_a_held_push_names_contract_run(self) -> None:
        fake = FakeTicketOnBranch(landing=Landing(unclosed=(SLUG,), unproven=('T1 open',)))
        verdict = await judge(bash_payload(PUSH), fake)
        assert (verdict.decision, 'contract_run' in verdict.detail) == ('deny', True)


class TestHookMatcher:
    def matcher(self) -> str:
        matchers = [
            hook.matcher
            for hook in read_registered_hooks()
            if hook.script == 'main-thread-hook.sh' and hook.matcher is not None
        ]
        assert len(matchers) == 1
        return matchers[0]

    @pytest.mark.parametrize(
        'tool',
        [
            CONTRACT_RUN_TOOL,
            CONTRACT_APPROVE_TOOL,
            CONTRACT_RETIRE_TOOL,
            'Edit',
            'Write',
            'Bash',
        ],
    )
    def test_it_matches_the_tool(self, tool: str) -> None:
        assert re.fullmatch(self.matcher(), tool)

    @pytest.mark.parametrize(
        'tool',
        [
            'Read',
            'Grep',
            'Editor',
            'mcp__plugin_mightymodels_mighty-mcp__task_start',
            f'{CONTRACT_RUN_TOOL}_extra',
            CONTRACT_RUN_TOOL.removeprefix('mcp__'),
        ],
    )
    def test_it_ignores_every_other_tool(self, tool: str) -> None:
        assert re.search(self.matcher(), tool) is None
