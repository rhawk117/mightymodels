from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest
from mcp import Client
from mightymodels_mcp.forms.needs_input import NEEDS_INPUT

from tests.mcp.forms.form_probes import (
    CHAIN_TOOL,
    ChainTool,
    ScriptedAnswerer,
    create_chain_catalog,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mcp.types import CallToolResult

    from tests.mcp.forms.form_probes import ElicitAction
    from tests.mcp.server.server_harness import ServerHarness


@dataclass(slots=True, kw_only=True, frozen=True)
class ChainHarness:
    server: ServerHarness
    tool: ChainTool

    async def call(self, answerer: ScriptedAnswerer, arguments: dict[str, str]) -> CallToolResult:
        server = self.server.create_server(create_chain_catalog(self.tool))
        async with Client(server, elicitation_callback=answerer.answer) as client:
            return await client.call_tool(CHAIN_TOOL, arguments)


def unanswered_action_cases() -> pytest.MarkDecorator:
    actions: list[ParameterSet] = [
        pytest.param('decline', id='decline'),
        pytest.param('cancel', id='cancel'),
    ]
    return pytest.mark.parametrize('action', actions)


def result_text(result: CallToolResult) -> str:
    assert result.structured_content
    return result.structured_content['text']


class TestChoiceRounds:
    arguments = MappingProxyType({'slug': 'probe-ticket'})
    answers = MappingProxyType({'mode': 'deep', 'depth': 'branch'})

    @pytest.fixture
    def harness(self, server_harness: ServerHarness) -> ChainHarness:
        return ChainHarness(server=server_harness, tool=ChainTool())

    async def test_two_round_chain_completes_in_one_call(self, harness: ChainHarness) -> None:
        answerer = ScriptedAnswerer(answers=dict(self.answers))

        result = await harness.call(answerer, dict(self.arguments))

        assert not result.is_error
        assert result.structured_content == {'text': 'deep branch'}
        assert answerer.messages == ['Choose a mode', 'Choose a depth for the deep review']

    async def test_supplied_arguments_ask_nothing(self, harness: ChainHarness) -> None:
        answerer = ScriptedAnswerer(answers={})

        result = await harness.call(answerer, {**self.arguments, **self.answers})

        assert result.structured_content == {'text': 'deep branch'}
        assert answerer.messages == []

    async def test_round_holds_only_the_omitted_fields(self, harness: ChainHarness) -> None:
        answerer = ScriptedAnswerer(answers={'depth': 'diff'})

        result = await harness.call(answerer, {**self.arguments, 'mode': 'quick'})

        assert result.structured_content == {'text': 'quick diff'}
        assert answerer.messages == ['Choose a depth for the quick review']

    @unanswered_action_cases()
    async def test_unanswered_round_returns_the_needs_input_text(
        self, harness: ChainHarness, action: ElicitAction
    ) -> None:
        answerer = ScriptedAnswerer(answers={}, action=action)

        result = await harness.call(answerer, dict(self.arguments))

        assert not result.is_error
        text = result_text(result)
        assert text.startswith(NEEDS_INPUT)
        assert 'choices: quick, deep\npass: mode\n' in text
        assert 'choices: diff, branch\npass: depth\n' in text

    async def test_answer_outside_the_choices_never_reaches_the_handler(
        self, harness: ChainHarness
    ) -> None:
        answerer = ScriptedAnswerer(answers={'mode': 'reckless', 'depth': 'diff'})

        result = await harness.call(answerer, dict(self.arguments))

        assert result.is_error
        assert 'does not match the requested schema' in str(result.content)
        assert harness.tool.handled == []
