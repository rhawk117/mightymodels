"""The session briefing as Markdown; strings read from the repository go in code spans."""

from collections.abc import Iterator, Mapping, Sequence
from datetime import date, datetime, time
from functools import singledispatch
from types import MappingProxyType

from python_harness.hooks.briefing.domain import (
    BriefingOptions,
    ConflictingPytestTables,
    Declaration,
    ExtendChainTooLong,
    ExtendCycle,
    ExtendTargetMissing,
    PackageFacts,
    ProjectScan,
    PythonFacts,
    RunnerBrief,
    Setting,
    SuiteFacts,
    Tool,
    ToolScan,
    UnreadableFile,
)
from python_harness.hooks.briefing.util.environments import (
    environment_differs_from_pin,
)
from python_harness.hooks.presentation import ELLIPSIS, code_span

HEADER = '## Python toolchain (pythonista session scan)'
TRUNCATION_MARK = '\n- (briefing truncated)'
LIST_SEPARATOR = ', '
WORD_SEPARATOR = ' '
WORD_SEPARATED_SETTINGS = frozenset({'addopts'})
DECLARATION_LABELS: Mapping[Declaration, str] = MappingProxyType(
    {
        Declaration.RUNTIME: 'runtime dependency',
        Declaration.DEVELOPMENT: 'dev dependency',
        Declaration.OPTIONAL: 'optional dependency',
        Declaration.UNDECLARED: 'not declared',
    }
)
MISSING_CONFIG = 'no project config found'
TOOL_COMMANDS: Mapping[Tool, tuple[str, ...]] = MappingProxyType(
    {
        Tool.RUFF: ('ruff check', 'ruff format'),
        Tool.TY: ('ty check',),
        Tool.PYTEST: ('pytest',),
    }
)


def cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + ELLIPSIS


def collapse(text: str) -> str:
    return ' '.join(text.split())


def quoted(text: str, limit: int) -> str:
    return code_span(cap(collapse(text), limit))


def join_items(items: Sequence[str], limit: int, separator: str) -> str:
    if not items:
        return 'none'
    shown = separator.join(items[:limit])
    hidden = len(items) - limit
    if hidden > 0:
        return f'{shown} (+{hidden} more)'
    return shown


def describe_scalar(value: str | float | date | time) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return collapse(str(value))


def describe_value(value: object, limit: int, separator: str = LIST_SEPARATOR) -> str:
    if isinstance(value, (str, int, float, date, datetime, time)):
        return describe_scalar(value)
    if isinstance(value, list):
        items = [describe_value(item, limit) for item in value]
        return join_items(items, limit, separator)
    if isinstance(value, Mapping):
        entries = [
            f'{collapse(str(key))} {describe_value(item, limit)}' for key, item in value.items()
        ]
        return join_items(entries, limit, LIST_SEPARATOR)
    return type(value).__name__


def describe_setting(setting: Setting, options: BriefingOptions) -> str:
    separator = WORD_SEPARATOR if setting.name in WORD_SEPARATED_SETTINGS else LIST_SEPARATOR
    value = describe_value(setting.value, options.list_limit, separator)
    return f'{setting.name} {code_span(cap(value, options.value_limit))}'


@singledispatch
def describe_problem(problem: object, _limit: int) -> str:
    return type(problem).__name__


@describe_problem.register
def describe_unreadable(problem: UnreadableFile, limit: int) -> str:
    return f'{quoted(problem.label, limit)} {cap(collapse(problem.reason), limit)}'


@describe_problem.register
def describe_cycle(problem: ExtendCycle, limit: int) -> str:
    return f'ruff extend cycle at {quoted(problem.path, limit)}'


@describe_problem.register
def describe_long_chain(problem: ExtendChainTooLong, _limit: int) -> str:
    return f'ruff extend chain is longer than {problem.limit} files'


@describe_problem.register
def describe_missing_target(problem: ExtendTargetMissing, limit: int) -> str:
    return f'ruff extend target {quoted(problem.path, limit)} does not exist'


@describe_problem.register
def describe_conflicting_tables(problem: ConflictingPytestTables, limit: int) -> str:
    return (
        f'{quoted(problem.path, limit)} has both [tool.pytest] and'
        ' [tool.pytest.ini_options], which pytest refuses'
    )


def describe_package(package: PackageFacts) -> str:
    label = DECLARATION_LABELS[package.declaration]
    if package.locked_version is None:
        return f'{package.name} ({label})'
    return f'{package.name} {code_span(package.locked_version)} ({label})'


def describe_config(tool: ToolScan, limit: int) -> str:
    source = tool.config
    if source is None:
        return MISSING_CONFIG
    if source.table is None:
        return quoted(source.path, limit)
    return f'{quoted(source.path, limit)} [{source.table}]'


def tool_parts(tool: ToolScan, options: BriefingOptions) -> Iterator[str]:
    limit = options.value_limit
    yield describe_config(tool, limit)
    yield from (describe_setting(setting, options) for setting in tool.settings)
    yield from (f'problem: {describe_problem(item, limit)}' for item in tool.problems)


def tool_line(tool: ToolScan, options: BriefingOptions) -> str:
    parts = '; '.join(tool_parts(tool, options))
    return f'- {describe_package(tool.package)}: {parts}'


def suite_parts(tests: SuiteFacts, options: BriefingOptions) -> Iterator[str]:
    yield from tool_parts(tests.runner, options)
    plugins = LIST_SEPARATOR.join(describe_package(plugin) for plugin in tests.plugins)
    yield f'plugins: {plugins or "none declared"}'
    if tests.orchestrators:
        named = (f'{item.name} ({item.source})' for item in tests.orchestrators)
        yield f'orchestrators: {LIST_SEPARATOR.join(named)}'
    if tests.directories:
        yield f'test directories: {LIST_SEPARATOR.join(tests.directories)}'


def suite_line(tests: SuiteFacts, options: BriefingOptions) -> str:
    runner = describe_package(tests.runner.package)
    return f'- Tests, {runner}: {"; ".join(suite_parts(tests, options))}'


def python_parts(python: PythonFacts, limit: int) -> Iterator[str]:
    pin = python.pin
    if pin is not None:
        yield f'pinned {quoted(pin.version, limit)} ({quoted(pin.path, limit)})'
    if python.requires_python is not None:
        yield f'requires-python {quoted(python.requires_python, limit)}'
    environment = python.environment
    if environment is None:
        return
    running = ' '.join(item for item in (environment.implementation, environment.version) if item)
    described = quoted(running, limit) if running else 'no version in pyvenv.cfg'
    location = quoted(environment.path, limit)
    yield f'{location}: {described}'
    pinned = None if pin is None else pin.version
    if environment_differs_from_pin(pinned, environment.version):
        yield f'{location} runs a different minor version than the pin'


def python_line(python: PythonFacts, limit: int) -> str:
    parts = '; '.join(python_parts(python, limit))
    return f'- Python: {parts or "no pin, no requires-python, no virtualenv"}'


def project_line(scan: ProjectScan, limit: int) -> str:
    manifest = scan.manifest or 'no pyproject.toml'
    files = LIST_SEPARATOR.join(scan.dependency_files) or 'none'
    directory = scan.dependency_directory
    located = '' if directory is None else f' in {quoted(directory, limit)}'
    root = collapse(scan.root)
    return f'- Root: {root} ({manifest}; dependency files{located}: {files})'


def declared_commands(scan: ProjectScan, runner: RunnerBrief) -> Iterator[str]:
    tools = (scan.ruff, scan.ty, scan.tests.runner)
    declared = (tool for tool in tools if tool.package.declaration != Declaration.UNDECLARED)
    for tool in declared:
        yield from (f'{runner.prefix} {command}' for command in TOOL_COMMANDS[tool.tool])


def commands_lines(scan: ProjectScan, runner: RunnerBrief) -> tuple[str, ...]:
    commands = LIST_SEPARATOR.join(map(code_span, declared_commands(scan, runner)))
    if not commands:
        return ()
    return (f'- Commands: {commands}',)


def problem_lines(scan: ProjectScan, limit: int) -> tuple[str, ...]:
    if not scan.problems:
        return ()
    described = '; '.join(describe_problem(problem, limit) for problem in scan.problems)
    return (f'- Could not read: {described}',)


def project_lines(
    scan: ProjectScan, options: BriefingOptions, runner: RunnerBrief
) -> Iterator[str]:
    yield project_line(scan, options.value_limit)
    yield python_line(scan.python, options.value_limit)
    yield runner.rule
    yield tool_line(scan.ruff, options)
    yield tool_line(scan.ty, options)
    yield suite_line(scan.tests, options)
    yield from commands_lines(scan, runner)
    yield from problem_lines(scan, options.value_limit)


def no_project_lines(scan: ProjectScan, runner: RunnerBrief) -> Iterator[str]:
    yield f'- No Python project files at or above {collapse(scan.root)}.'
    yield runner.rule


def truncate_briefing(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(TRUNCATION_MARK)] + TRUNCATION_MARK


def render_session_context(scan: ProjectScan, options: BriefingOptions, runner: RunnerBrief) -> str:
    lines = (
        project_lines(scan, options, runner)
        if scan.has_python_markers
        else no_project_lines(scan, runner)
    )
    return truncate_briefing('\n'.join((HEADER, *lines)), options.context_limit)
