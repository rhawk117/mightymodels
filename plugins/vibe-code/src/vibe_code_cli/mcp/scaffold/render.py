import re
import shutil
from pathlib import Path

import msgspec

from vibe_code_cli.findings import CannotCheckError
from vibe_code_cli.mcp.scaffold.config import render_config
from vibe_code_cli.mcp.scaffold.server import server_tokens
from vibe_code_cli.mcp.scaffold.spec import LoadedSpec, Spec
from vibe_code_cli.mcp.scaffold.text import wrap_literal
from vibe_code_cli.mcp.scaffold.tool import render_schema, render_test, render_use_case
from vibe_code_cli.plugin.manifest import json_text

ROOT_VARIABLE = 'CLAUDE_PROJECT_DIR'
ROOT_VARIABLE_SOURCES = ('env', 'roots')
TRANSPORT_REACHES = (('stdio', ('local', 'both')), ('streamable-http', ('network', 'both')))
TOKEN = re.compile(r'(__[A-Z][A-Z_]*__)')


def template_tokens(spec: Spec) -> dict[str, str]:
    transports = ''.join(
        f'{transport!r}, ' for transport, reaches in TRANSPORT_REACHES if spec.reach in reaches
    )
    reads_variable = spec.root_source in ROOT_VARIABLE_SOURCES
    return {
        **server_tokens(spec),
        '__PKG__': spec.package,
        '__NAME__': spec.name,
        '__DESCRIPTION__': spec.description,
        '__DESCRIPTION_TOML__': msgspec.json.encode(spec.description).decode()[1:-1],
        '__DESCRIPTION_LITERAL__': wrap_literal(spec.description),
        '__INSTRUCTIONS_LITERAL__': wrap_literal(spec.instructions),
        '__TRANSPORTS__': transports,
        '__ROOT_VARIABLE__': repr(ROOT_VARIABLE) if reads_variable else 'None',
    }


def substitute(text: str, tokens: dict[str, str]) -> str:
    pieces = TOKEN.split(text)
    return ''.join(map(tokens.get, pieces, pieces))


def in_tool_cache(relative: Path) -> bool:
    return any(name.startswith('.') or name == '__pycache__' for name in relative.parts[:-1])


def plan_project(loaded: LoadedSpec, template_dir: Path) -> dict[str, str]:
    spec = loaded.spec
    tokens = template_tokens(spec)
    package_dir = f'src/{spec.package}'
    plan = {'tests/__init__.py': ''}
    try:
        for source in sorted(template_dir.rglob('*')):
            if source.is_file() and not in_tool_cache(source.relative_to(template_dir)):
                relative = substitute(source.relative_to(template_dir).as_posix(), tokens)
                plan[relative] = substitute(source.read_text(encoding='utf-8'), tokens)
    except (OSError, UnicodeError) as problem:
        message = f'cannot read the template {template_dir}: {type(problem).__name__}'
        raise CannotCheckError(message) from problem
    for tool in spec.tools:
        tool_dir = f'{package_dir}/tools/{tool.name}'
        plan[f'{tool_dir}/__init__.py'] = f'"""{tool.name} tool package."""\n'
        plan[f'{tool_dir}/schema.py'] = render_schema(tool)
        plan[f'{tool_dir}/use_case.py'] = render_use_case(spec, tool)
        plan[f'tests/test_{tool.name}.py'] = render_test(spec, tool)
    for filename, content in render_config(spec).items():
        plan[f'config/{filename}'] = content
    plan['mcp-spec.json'] = json_text(loaded.record)
    return plan


def write_project(target: Path, plan: dict[str, str], *, force: bool) -> None:
    root = target.resolve()
    destinations = {relative: (root / relative).resolve() for relative in plan}
    outside = [relative for relative, path in destinations.items() if not path.is_relative_to(root)]
    if outside:
        message = f'refusing to write outside {target}: {len(outside)} path(s) escape it'
        raise CannotCheckError(message)
    source_dir = root / 'src'
    if force and source_dir.is_dir() and not source_dir.is_symlink():
        shutil.rmtree(source_dir)
    try:
        for relative, text in plan.items():
            destinations[relative].parent.mkdir(parents=True, exist_ok=True)
            destinations[relative].write_text(text, encoding='utf-8')
    except OSError as problem:
        message = f'cannot write under {target}: {problem}'
        raise CannotCheckError(message) from problem
