"""Which verification commands run, how they launch and which ruff config applies."""

import json
from collections.abc import Iterable
from pathlib import Path

from python_harness.gate.domain import (
    GateCommand,
    GateInputs,
    GateOptions,
    GatePlan,
    GateTool,
    Launcher,
    RuffConfigSelection,
    RuffConfigSource,
    ToolInvocation,
)


def list_ruff_source_roots(inputs: GateInputs, workspace_root: Path) -> tuple[Path, ...]:
    found = (workspace_root.joinpath(root) for root in inputs.source_roots)
    return (*found, workspace_root)


def build_source_roots_override(roots: Iterable[Path]) -> str:
    return f'src = {json.dumps([root.as_posix() for root in roots])}'


def select_ruff_config(
    inputs: GateInputs, workspace_root: Path, options: GateOptions
) -> RuffConfigSelection:
    fallback = options.fallback_ruff_config
    if inputs.has_ruff_config:
        return RuffConfigSelection(RuffConfigSource.REPOSITORY, ())
    if fallback is None:
        return RuffConfigSelection(RuffConfigSource.DEFAULTS, ())
    source_roots = list_ruff_source_roots(inputs, workspace_root)
    arguments = (
        '--config',
        fallback.as_posix(),
        '--config',
        build_source_roots_override(source_roots),
    )
    return RuffConfigSelection(RuffConfigSource.FALLBACK, arguments)


def project_launcher(inputs: GateInputs) -> Launcher:
    if inputs.has_uv_lock:
        return Launcher('uv', ('run', '--isolated', '--frozen'))
    return Launcher('uv', ('run', '--isolated'))


def choose_launcher(invocation: ToolInvocation, inputs: GateInputs) -> Launcher:
    project = project_launcher(inputs)
    if invocation.distribution in inputs.declared_distributions:
        return project
    if invocation.runs_in_project_environment:
        joined = (*project.arguments, '--with', invocation.distribution)
        return Launcher(project.program, joined)
    return Launcher('uvx')


def build_command(
    tool: GateTool,
    inputs: GateInputs,
    ruff_config: RuffConfigSelection,
    *,
    options: GateOptions,
) -> GateCommand:
    invocation = options.tools[tool]
    launcher = choose_launcher(invocation, inputs)
    config = ruff_config.arguments if invocation.reads_ruff_config else ()
    arguments = (*launcher.arguments, *invocation.arguments, *config)
    return GateCommand(tool, launcher.program, arguments)


def is_tool_planned(tool: GateTool, inputs: GateInputs, options: GateOptions) -> bool:
    if tool in options.skipped:
        return False
    required = options.tools[tool].required_domain
    return required is None or required in inputs.domains


def plan_gate(
    inputs: GateInputs, workspace_root: Path, options: GateOptions | None = None
) -> GatePlan:
    chosen = GateOptions() if options is None else options
    ruff_config = select_ruff_config(inputs, workspace_root, chosen)
    planned = (tool for tool in chosen.tools if is_tool_planned(tool, inputs, chosen))
    commands = tuple(build_command(tool, inputs, ruff_config, options=chosen) for tool in planned)
    return GatePlan(commands, ruff_config.source)
