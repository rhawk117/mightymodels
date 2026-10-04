import msgspec
import pytest
from ai_engineer_cli.hook.schema import (
    AgentHook,
    CommandHook,
    EventName,
    HookHandler,
    HttpHook,
    McpToolHook,
    PromptHook,
)

HANDLERS = [
    (
        {'type': 'command', 'command': 'x', 'args': ['a'], 'shell': 'bash', 'asyncRewake': True},
        CommandHook,
    ),
    (
        {'type': 'http', 'url': 'https://x', 'headers': {'A': 'b'}, 'allowedEnvVars': ['A']},
        HttpHook,
    ),
    ({'type': 'mcp_tool', 'server': 's', 'tool': 't', 'input': {'k': 1}}, McpToolHook),
    ({'type': 'prompt', 'prompt': 'p', 'model': 'm'}, PromptHook),
    ({'type': 'agent', 'prompt': 'p', 'if': 'Bash(git *)', 'once': True}, AgentHook),
]


@pytest.mark.parametrize(('raw', 'expected'), HANDLERS)
def test_each_documented_handler_type_converts_to_its_struct(
    raw: dict[str, object], expected: type[msgspec.Struct]
) -> None:
    assert type(msgspec.convert(raw, HookHandler)) is expected


@pytest.mark.parametrize(
    ('raw', 'message'),
    [
        ({'command': 'x'}, 'Object missing required field `type`'),
        ({'type': 'command'}, 'Object missing required field `command`'),
        ({'type': 'http'}, 'Object missing required field `url`'),
        ({'type': 'mcp_tool', 'server': 's'}, 'Object missing required field `tool`'),
        ({'type': 'prompt'}, 'Object missing required field `prompt`'),
        ({'type': 'command', 'command': 'x', 'timeout': 'x'}, 'Expected `int | float`'),
        ({'type': 'command', 'command': 'x', 'shell': 'zsh'}, 'Invalid enum value'),
        ({'type': 'http', 'url': 'u', 'url2': 'v'}, 'Object contains unknown field `url2`'),
        ({'type': 'prompt', 'prompt': 'p', 'command': 'x'}, 'Object contains unknown field'),
    ],
)
def test_a_handler_the_field_tables_do_not_allow_is_a_validation_error(
    raw: dict[str, object], message: str
) -> None:
    with pytest.raises(msgspec.ValidationError, match=message):
        msgspec.convert(raw, HookHandler)


def test_event_name_is_every_event_of_the_event_table() -> None:
    assert len(EventName.__args__) == 33
    assert msgspec.convert('SessionEnd', EventName) == 'SessionEnd'
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert('sessionEnd', EventName)
