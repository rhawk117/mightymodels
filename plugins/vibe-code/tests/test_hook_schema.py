import msgspec
import pytest
from vibe_code_cli.hook.schema import (
    AgentHook,
    CommandHook,
    EventName,
    HookHandler,
    HttpHook,
    McpToolHook,
    PromptHook,
)


class TestHandlerTypes:
    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            pytest.param(
                {
                    'type': 'command',
                    'command': 'x',
                    'args': ['a'],
                    'shell': 'bash',
                    'asyncRewake': True,
                },
                CommandHook,
                id='raw0-CommandHook',
            ),
            pytest.param(
                {
                    'type': 'http',
                    'url': 'https://x',
                    'headers': {'A': 'b'},
                    'allowedEnvVars': ['A'],
                },
                HttpHook,
                id='raw1-HttpHook',
            ),
            pytest.param(
                {'type': 'mcp_tool', 'server': 's', 'tool': 't', 'input': {'k': 1}},
                McpToolHook,
                id='raw2-McpToolHook',
            ),
            pytest.param(
                {'type': 'prompt', 'prompt': 'p', 'model': 'm'}, PromptHook, id='raw3-PromptHook'
            ),
            pytest.param(
                {'type': 'agent', 'prompt': 'p', 'if': 'Bash(git *)', 'once': True},
                AgentHook,
                id='raw4-AgentHook',
            ),
        ],
    )
    def test_each_documented_handler_type_converts_to_its_struct(
        self, raw: dict[str, object], expected: type[msgspec.Struct]
    ) -> None:
        assert type(msgspec.convert(raw, HookHandler)) is expected


class TestFieldTables:
    @pytest.mark.parametrize(
        ('raw', 'message'),
        [
            pytest.param(
                {'command': 'x'},
                'Object missing required field `type`',
                id='raw0-Object missing required field `type`',
            ),
            pytest.param(
                {'type': 'command'},
                'Object missing required field `command`',
                id='raw1-Object missing required field `command`',
            ),
            pytest.param(
                {'type': 'http'},
                'Object missing required field `url`',
                id='raw2-Object missing required field `url`',
            ),
            pytest.param(
                {'type': 'mcp_tool', 'server': 's'},
                'Object missing required field `tool`',
                id='raw3-Object missing required field `tool`',
            ),
            pytest.param(
                {'type': 'prompt'},
                'Object missing required field `prompt`',
                id='raw4-Object missing required field `prompt`',
            ),
            pytest.param(
                {'type': 'command', 'command': 'x', 'timeout': 'x'},
                'Expected `int | float`',
                id='raw5-Expected `int | float`',
            ),
            pytest.param(
                {'type': 'command', 'command': 'x', 'shell': 'zsh'},
                'Invalid enum value',
                id='raw6-Invalid enum value',
            ),
            pytest.param(
                {'type': 'http', 'url': 'u', 'url2': 'v'},
                'Object contains unknown field `url2`',
                id='raw7-Object contains unknown field `url2`',
            ),
            pytest.param(
                {'type': 'prompt', 'prompt': 'p', 'command': 'x'},
                'Object contains unknown field',
                id='raw8-Object contains unknown field',
            ),
        ],
    )
    def test_a_handler_the_field_tables_do_not_allow_is_a_validation_error(
        self, raw: dict[str, object], message: str
    ) -> None:
        with pytest.raises(msgspec.ValidationError, match=message):
            msgspec.convert(raw, HookHandler)


class TestEventName:
    def test_event_name_is_every_event_of_the_event_table(self) -> None:
        assert len(EventName.__args__) == 33
        assert msgspec.convert('SessionEnd', EventName) == 'SessionEnd'
        with pytest.raises(msgspec.ValidationError):
            msgspec.convert('sessionEnd', EventName)
