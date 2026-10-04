from msgspec import UnsetType

from vibe_code_cli.mcp.scaffold.spec import Parameter, Spec, Tool
from vibe_code_cli.mcp.scaffold.text import docstring, wrap_literal

EXAMPLES = {
    'str': "'example'",
    'int': '1',
    'float': '1.0',
    'bool': 'True',
    'list[str]': "['example']",
    'list[int]': '[1]',
    'dict[str, str]': "{'key': 'value'}",
    'list[dict[str, str]]': "[{'key': 'value'}]",
}
COMMAND_FAILED = "        raise ToolError(result.error or result.stderr or 'command failed')"


def render_field(parameter: Parameter) -> str:
    description = wrap_literal(parameter.description, width=60).replace('\n', '\n    ')
    if parameter.required:
        return f'    {parameter.name}: {parameter.type} = Field(description={description})'
    default = None if isinstance(parameter.default, UnsetType) else parameter.default
    if default is None:
        return (
            f'    {parameter.name}: {parameter.type} | None = Field('
            f'default=None, description={description})'
        )
    return (
        f'    {parameter.name}: {parameter.type} = Field('
        f'default={default!r}, description={description})'
    )


def render_schema(tool: Tool) -> str:
    lines = [
        f'"""Input and output models for the {tool.name} tool."""',
        '',
        'from __future__ import annotations',
        '',
        'from pydantic import BaseModel, Field',
        '',
        '',
        'class Input(BaseModel):',
    ]
    lines += [render_field(parameter) for parameter in tool.inputs] or ['    pass']
    lines += ['', '', 'class Output(BaseModel):']
    lines += [render_field(parameter) for parameter in tool.outputs]
    if tool.confirm:
        lines += [
            '',
            '',
            'class Confirm(BaseModel):',
            (
                '    proceed: bool = Field(description='
                "'True to go ahead, False to stop without changing anything.')"
            ),
        ]
    return '\n'.join(lines) + '\n'


def auto_mappable(tool: Tool) -> bool:
    inputs = [parameter for parameter in tool.inputs if parameter.name != 'root']
    return (
        bool(tool.binary)
        and not inputs
        and all(parameter.type in ('str', 'list[str]') for parameter in tool.outputs)
    )


def render_use_case(spec: Spec, tool: Tool) -> str:
    mapped = auto_mappable(tool)
    lines = [
        docstring(tool.name, tool.description),
        '',
        'from __future__ import annotations',
        '',
        'from typing import TYPE_CHECKING',
        '',
    ]
    if tool.binary:
        lines += ['from mcp.server.mcpserver.exceptions import ToolError', '']
    lines += use_case_imports(spec.package, tool, mapped=mapped)
    lines += ['def run(workspace: RepositoryWorkspace, params: Input) -> Output:']
    lines += use_case_body(tool, mapped=mapped)
    return '\n'.join(lines) + '\n'


def use_case_imports(package: str, tool: Tool, *, mapped: bool) -> list[str]:
    schema_import = f'from {package}.tools.{tool.name}.schema import Input, Output'
    workspace_import = f'    from {package}.workspace import RepositoryWorkspace'
    if mapped:
        return [schema_import, '', 'if TYPE_CHECKING:', workspace_import, '', '']
    return ['if TYPE_CHECKING:', f'    {schema_import}', workspace_import, '', '']


def use_case_body(tool: Tool, *, mapped: bool) -> list[str]:
    name = tool.name
    if not tool.binary:
        return [
            (
                f"    message = f'{name} is not implemented yet "
                f"(root {{workspace.root}}, params {{params!r}})'"
            ),
            '    raise NotImplementedError(message)',
        ]
    arguments = ', '.join(repr(argument) for argument in tool.arguments)
    run = f'    result = workspace.execute_tool(binary={tool.binary!r}, arguments=[{arguments}])'
    if not mapped:
        return [
            run,
            '    if not result.succeeded:',
            COMMAND_FAILED,
            '    preview = result.stdout[:200]',
            (
                f"    message = f'{name}: map the command output "
                f"into Output ({{params!r}}, {{preview!r}})'"
            ),
            '    raise NotImplementedError(message)',
        ]
    outputs = ', '.join(
        f'{parameter.name}='
        f'{"result.stdout" if parameter.type == "str" else "result.stdout.splitlines()"}'
        for parameter in tool.outputs
    )
    return [
        '    del params  # uniform use-case signature; this tool takes no inputs',
        run,
        '    if not result.succeeded:',
        COMMAND_FAILED,
        f'    return Output({outputs})',
    ]


def render_test(spec: Spec, tool: Tool) -> str:
    package = spec.package
    name = tool.name
    lines = [
        f'"""Contract tests for the {name} tool, run in-process through the MCP client."""',
        '',
        'from __future__ import annotations',
        '',
        'from pathlib import Path',
        '',
        'from mcp import Client',
    ]
    if tool.confirm:
        lines += [
            'from mcp.client.session import ClientRequestContext',
            'from mcp.types import ElicitRequestParams, ElicitResult',
        ]
    lines += ['', f'from {package}.server import build_server', '', '']
    lines += listing_test(tool)
    lines += call_test(tool)
    return '\n'.join(lines) + '\n'


def listing_test(tool: Tool) -> list[str]:
    name = tool.name
    lines = [
        f'async def test_{name}_is_listed_with_its_schema(tmp_path: Path) -> None:',
        '    async with Client(build_server(tmp_path), raise_exceptions=True) as client:',
        '        tools = {tool.name: tool for tool in (await client.list_tools()).tools}',
        f"    assert '{name}' in tools",
    ]
    if tool.inputs:
        lines += [f"    properties = tools['{name}'].input_schema['$defs']['Input']['properties']"]
        lines += [f"    assert '{parameter.name}' in properties" for parameter in tool.inputs]
    lines += [
        f"    assert tools['{name}'].annotations is not None",
        (
            f"    assert tools['{name}'].annotations.read_only_hint is "
            f'{tool.side_effects == "read_only"}'
        ),
        '',
        '',
    ]
    return lines


def call_test(tool: Tool) -> list[str]:
    name = tool.name
    arguments = ', '.join(
        f"'{parameter.name}': "
        f'{"str(tmp_path)" if parameter.name == "root" else EXAMPLES[parameter.type]}'
        for parameter in tool.inputs
        if parameter.required
    )
    lines: list[str] = []
    client_line = '    async with Client(build_server(tmp_path), raise_exceptions=True) as client:'
    if tool.confirm:
        lines += [
            (
                'async def accept(context: ClientRequestContext, '
                'params: ElicitRequestParams) -> ElicitResult:'
            ),
            '    del context, params',
            "    return ElicitResult(action='accept', content={'proceed': True})",
            '',
            '',
        ]
        client_line = (
            '    async with Client(build_server(tmp_path), '
            'raise_exceptions=True, elicitation_callback=accept) as client:'
        )
    lines += [
        f'async def test_{name}_returns_structured_output(tmp_path: Path) -> None:',
        client_line,
        f"        result = await client.call_tool('{name}', {{'params': {{{arguments}}}}})",
        '    assert not result.is_error',
        '    assert result.structured_content is not None',
    ]
    lines += [
        f"    assert '{parameter.name}' in result.structured_content" for parameter in tool.outputs
    ]
    return lines
