import argparse
import os
import sys
from pathlib import Path

from ai_engineer_cli.findings import CannotCheckError
from ai_engineer_cli.scaffold_render import plan_project, write_project
from ai_engineer_cli.scaffold_spec import Spec, load_spec, spec_warnings

PLUGIN_ROOT_VARIABLE = 'AI_ENGINEER_PLUGIN_ROOT'
TEMPLATE_PATH = Path('skills') / 'create-mcp' / 'assets' / 'template'


def default_template() -> Path:
    """The skill's template: under the root the shim exports, else under this package's plugin."""
    exported = os.environ.get(PLUGIN_ROOT_VARIABLE)
    plugin_root = Path(exported) if exported else Path(__file__).resolve().parents[2]
    return plugin_root / TEMPLATE_PATH


def scaffold_command(arguments: argparse.Namespace) -> int:
    """Return 0 once the project is written, 2 for a spec, template or target it rejects."""
    try:
        spec, plan = prepare(arguments)
        write_project(arguments.target, plan, force=arguments.force)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2
    for warning in spec_warnings(spec):
        print(f'warning: {warning}', file=sys.stderr)
    for relative in plan:
        print(f'wrote {relative}')
    print(
        f'{len(plan)} file(s) under {arguments.target}; next: cd {arguments.target} && uv sync '
        '&& uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest'
    )
    return 0


def prepare(arguments: argparse.Namespace) -> tuple[Spec, dict[str, str]]:
    """Validate the inputs and build every file in memory, so a rejection writes nothing."""
    template = arguments.template or default_template()
    target = arguments.target
    if not template.is_dir():
        message = f'template {template} is not a directory'
        raise CannotCheckError(message)
    spec = load_spec(arguments.spec)
    occupied = target.exists() and (not target.is_dir() or any(target.iterdir()))
    if occupied and not arguments.force:
        message = f'{target} is not empty; pass --force to overwrite template-owned files'
        raise CannotCheckError(message)
    return spec, plan_project(spec, template)
