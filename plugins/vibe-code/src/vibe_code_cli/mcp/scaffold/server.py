from msgspec import UnsetType

from vibe_code_cli.mcp.scaffold.spec import PLACEHOLDER, Prompt, Resource, Spec, Tool
from vibe_code_cli.mcp.scaffold.text import wrap_literal

REQUIRES_INTERACTION_KEY = 'anthropic/requiresUserInteraction'
MAX_RESULT_SIZE_KEY = 'anthropic/maxResultSizeChars'
ROOTS_HELPER = """

async def roots_workspace_of(ctx: Context[AppState]) -> RepositoryWorkspace:
    workspace = ctx.request_context.lifespan_context.workspace
    root = await listed_root(ctx.request_context.session)
    if root is None:
        return workspace
    return RepositoryWorkspace(workspace.workspace_tools, root)
"""


def tool_meta(tool: Tool) -> dict[str, bool | int]:
    meta: dict[str, bool | int] = {}
    if tool.side_effects == 'destructive':
        meta[REQUIRES_INTERACTION_KEY] = True
    if not isinstance(tool.max_result_chars, UnsetType):
        meta[MAX_RESULT_SIZE_KEY] = tool.max_result_chars
    return meta


def render_decorator(tool: Tool) -> str:
    read_only = tool.side_effects == 'read_only'
    destructive = tool.side_effects == 'destructive'
    annotations = (
        f'ToolAnnotations(read_only_hint={read_only}, '
        f'destructive_hint={destructive}, idempotent_hint={read_only}, '
        'open_world_hint=False)'
    )
    description = wrap_literal(tool.description, width=70).replace('\n', '\n    ')
    meta = tool_meta(tool)
    meta_argument = f', meta={meta!r}' if meta else ''
    return (
        f'    @mcp.tool(name={tool.name!r}, description={description}, '
        f'annotations={annotations}{meta_argument})'
    )


def run_lines(spec: Spec, tool: Tool, indent: str) -> list[str]:
    name = tool.name
    if spec.root_source == 'roots':
        return [
            f'{indent}workspace = await roots_workspace_of(ctx)',
            f'{indent}return await asyncio.to_thread({name}_use_case.run, workspace, params)',
        ]
    workspace_call = (
        'workspace_of(ctx, params.root)' if spec.root_source == 'parameter' else 'workspace_of(ctx)'
    )
    return [f'{indent}return {name}_use_case.run({workspace_call}, params)']


def render_registration(spec: Spec, tool: Tool) -> str:
    name = tool.name
    keyword = 'async def' if spec.root_source == 'roots' else 'def'
    lines: list[str] = []
    if not tool.confirm:
        lines += [
            render_decorator(tool),
            (
                f'    {keyword} {name}(params: {name}_schema.Input, ctx: '
                f'Context[AppState]) -> {name}_schema.Output:'
            ),
            *run_lines(spec, tool, '        '),
            '',
        ]
        return '\n'.join(lines)
    lines += [
        (
            f'    async def confirm_{name}(params: '
            f'{name}_schema.Input) -> {name}_schema.Confirm | '
            f'Elicit[{name}_schema.Confirm]:'
        ),
        (
            f"        return Elicit(f'About to run {name} with {{params!r}}. "
            f"Proceed?', {name}_schema.Confirm)"
        ),
        '',
        render_decorator(tool),
        (
            f'    {keyword} {name}(params: {name}_schema.Input, '
            f'confirmation: Annotated[ElicitationResult[{name}_schema.Confirm], '
            f'Resolve(confirm_{name})], ctx: Context[AppState]) -> '
            f'{name}_schema.Output:'
        ),
        '        match confirmation:',
        f'            case AcceptedElicitation(data={name}_schema.Confirm(proceed=True)):',
        *run_lines(spec, tool, '                '),
        '            case _:',
        f"                cancelled = '{name} cancelled by the user; nothing was changed'",
        '                raise ToolError(cancelled)',
        '',
    ]
    return '\n'.join(lines)


def render_resource(resource: Resource) -> str:
    function = resource.name
    signature = ', '.join(f'{parameter}: str' for parameter in PLACEHOLDER.findall(resource.uri))
    return '\n'.join(
        [
            (
                f'    @mcp.resource({resource.uri!r}, name={function!r}, '
                f'description={resource.description!r}, '
                f'mime_type={resource.mime_type!r})'
            ),
            f'    def {function}({signature}) -> str:',
            f"        message = 'resource {function} is not implemented yet'",
            '        raise NotImplementedError(message)',
            '',
        ]
    )


def render_prompt(prompt: Prompt) -> str:
    signature = ', '.join(f'{argument.name}: str' for argument in prompt.arguments)
    return '\n'.join(
        [
            f'    @mcp.prompt(name={prompt.name!r}, description={prompt.description!r})',
            f'    def {prompt.name}({signature}) -> str:',
            f'        return f{prompt.template!r}',
            '',
        ]
    )


def server_tokens(spec: Spec) -> dict[str, str]:
    """The server.py placeholders and the text each one becomes for this spec."""
    package = spec.package
    confirming = any(tool.confirm for tool in spec.tools)
    roots = spec.root_source == 'roots'
    imports = sorted(
        line
        for tool in spec.tools
        for line in (
            f'from {package}.tools.{tool.name} import schema as {tool.name}_schema',
            f'from {package}.tools.{tool.name} import use_case as {tool.name}_use_case',
        )
    )
    registrations = [render_registration(spec, tool) for tool in spec.tools]
    registrations += [render_resource(resource) for resource in spec.resources]
    registrations += [render_prompt(prompt) for prompt in spec.prompts]
    return {
        '__ASYNCIO_IMPORT__': 'import asyncio\n' if roots else '',
        '__TYPING_IMPORT__': '\nfrom typing import Annotated' if confirming else '',
        '__MCP_EXTRA__': (
            'AcceptedElicitation, Context, Elicit, ElicitationResult, Resolve'
            if confirming
            else 'Context'
        ),
        '__MCP_ERROR_IMPORT__': (
            'from mcp.server.mcpserver.exceptions import ToolError\n' if confirming else ''
        ),
        '__TOOL_IMPORTS__': '\n'.join(imports),
        '__WORKSPACE_IMPORTS__': (
            'RepositoryWorkspace, WorkspaceTool, current_workspace'
            + (', listed_root' if roots else '')
        ),
        '__ROOTS_HELPER__': ROOTS_HELPER if roots else '',
        '__TOOL_REGISTRATIONS__': '\n' + '\n'.join(registrations),
        '__BINARIES__': ''.join(f'{binary!r}, ' for binary in spec.binaries),
    }
