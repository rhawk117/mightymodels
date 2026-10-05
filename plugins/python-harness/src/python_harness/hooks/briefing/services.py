"""Scanning the Python toolchain a session starts in, reading files only.

Each fact is searched from the project directory up to the repository root, nearest
first, as ruff, ty, pytest and uv search; nothing runs, nothing is written or fetched.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from types import MappingProxyType

from python_harness.core.files import parse_version_pin
from python_harness.core.workspace import (
    DiscoveryOptions,
)
from python_harness.hooks.briefing.domain import (
    BriefingOptions,
    ConfigSource,
    ConfigTable,
    ExtendChainTooLong,
    ExtendCycle,
    ExtendTargetMissing,
    ExtendTargetOutside,
    IniDocument,
    MissingFile,
    Orchestrator,
    PackageFacts,
    ProjectScan,
    PytestCandidate,
    PytestConfig,
    PythonFacts,
    PythonPin,
    RunnerBrief,
    ScanOptions,
    ScanProblem,
    Setting,
    SuiteFacts,
    TextFile,
    TomlDocument,
    Tool,
    ToolScan,
    UnreadableFile,
    VirtualEnvironment,
)
from python_harness.hooks.briefing.policy import (
    PYTEST_CANDIDATES,
    pytest_from_ini,
    pytest_from_toml,
)
from python_harness.hooks.briefing.store import (
    ScanContext,
    has_directory,
    has_file,
    open_scan_context,
    read_text,
    read_toml,
)
from python_harness.hooks.briefing.util.configs import (
    PYTEST_SETTINGS,
    RUFF_SETTINGS,
    TY_SETTINGS,
    collect_settings,
    expand_variables,
    merge_chain,
    resolve_rule_selection,
    selection_settings,
)
from python_harness.hooks.briefing.util.environments import (
    environment_from_config,
    parse_pyvenv_config,
)
from python_harness.hooks.briefing.util.presentation import render_session_context
from python_harness.hooks.guard.domain import GuardOptions
from python_harness.hooks.guard.util.presentation import describe_guard_rule
from python_harness.survey.domain import PYPROJECT, ProjectManifest
from python_harness.survey.services import ruff_config_name
from python_harness.survey.util import (
    read_nested_table,
    read_string,
)

PYVENV_CONFIG = 'pyvenv.cfg'
TY_CONFIG = 'ty.toml'
TY_TABLE = ('tool', 'ty')
TOX_TABLE = ('tool', 'tox')
INI_OPTIONS = 'ini_options'
TOX_SECTION = 'tox'
TOX_ENVIRONMENT_PREFIX = 'testenv'
EMPTY_TABLE: ConfigTable = MappingProxyType({})
EMPTY_CONFIG: Mapping[str, str] = MappingProxyType[str, str]({})


@dataclass(frozen=True, slots=True)
class FoundConfig:
    path: Path
    source: ConfigSource


@dataclass(frozen=True, slots=True)
class ExtendTarget:
    path: Path
    written: str


@dataclass(frozen=True, slots=True)
class RuffChain:
    tables: tuple[ConfigTable, ...]
    extended: tuple[str, ...]
    problems: tuple[ScanProblem, ...]


def find_pin(context: ScanContext) -> PythonPin | None:
    name = context.options.version_file_name
    directory = context.find_directory(partial(has_file, name=name))
    if directory is None:
        return None
    path = directory.joinpath(name)
    read = read_text(path, context.display(path), context.options.max_file_bytes)
    version = parse_version_pin(read.text) if isinstance(read, TextFile) else None
    if version is None:
        return None
    return PythonPin(version, context.display(path))


def find_environment(context: ScanContext) -> VirtualEnvironment | None:
    name = context.options.environment_name
    directory = context.find_project_directory(partial(has_directory, name=name))
    if directory is None:
        return None
    path = directory.joinpath(name, PYVENV_CONFIG)
    read = read_text(path, context.display(path), context.options.max_file_bytes)
    config = parse_pyvenv_config(read.text) if isinstance(read, TextFile) else EMPTY_CONFIG
    return environment_from_config(context.display(directory.joinpath(name)), config)


def scan_python(context: ScanContext) -> PythonFacts:
    manifest = context.manifest
    return PythonFacts(
        pin=find_pin(context),
        requires_python=None if manifest is None else manifest.requires_python,
        environment=find_environment(context),
    )


def ruff_config_in(directory: Path, context: ScanContext) -> FoundConfig | None:
    name = ruff_config_name(directory, context.pyproject_table(directory))
    if name is None:
        return None
    path = directory.joinpath(name)
    table = f'tool.{Tool.RUFF}' if name == PYPROJECT else None
    return FoundConfig(path, ConfigSource(context.display(path), table))


def ruff_table_of(document: ConfigTable, path: Path) -> ConfigTable:
    if path.name == PYPROJECT:
        return read_nested_table(document, 'tool', Tool.RUFF)
    return document


def extend_target(
    table: ConfigTable, config_path: Path, context: ScanContext
) -> ExtendTarget | None:
    extend = read_string(table, 'extend')
    if extend is None:
        return None
    expanded = Path(expand_variables(extend, context.variables)).expanduser()
    return ExtendTarget(config_path.parent.joinpath(expanded), extend)


def find_chain_stop(
    target: ExtendTarget, visited: frozenset[Path], context: ScanContext
) -> ScanProblem | None:
    resolved = target.path.resolve()
    if not resolved.is_relative_to(context.boundary.resolve()):
        return ExtendTargetOutside(target.written)
    if resolved in visited:
        return ExtendCycle(target.written)
    limit = context.options.max_extend_depth
    if len(visited) >= limit:
        return ExtendChainTooLong(limit)
    return None


def extend_chain(
    table: ConfigTable, path: Path, context: ScanContext, *, visited: frozenset[Path]
) -> RuffChain:
    target = extend_target(table, path, context)
    if target is None:
        return RuffChain((table,), (), ())
    stop = find_chain_stop(target, visited, context)
    if stop is not None:
        return RuffChain((table,), (), (stop,))
    seen = visited | {target.path.resolve()}
    parent = load_ruff_chain(target.path, target.written, context, visited=seen)
    extended = (target.written, *parent.extended)
    return RuffChain((table, *parent.tables), extended, parent.problems)


def load_ruff_chain(
    path: Path, label: str, context: ScanContext, *, visited: frozenset[Path]
) -> RuffChain:
    read = read_toml(path, label, context.options.max_file_bytes)
    if isinstance(read, UnreadableFile):
        return RuffChain((), (), (read,))
    if isinstance(read, MissingFile):
        return RuffChain((), (), (ExtendTargetMissing(label),))
    table = ruff_table_of(read.table, path)
    return extend_chain(table, path, context, visited=visited)


def extends_settings(loaded: RuffChain) -> tuple[Setting, ...]:
    if not loaded.extended:
        return ()
    return (Setting('extends', list(loaded.extended)),)


def scan_ruff(context: ScanContext) -> ToolScan:
    package = context.package(Tool.RUFF)
    configs = (ruff_config_in(directory, context) for directory in context.directories)
    found = next((config for config in configs if config is not None), None)
    if found is None:
        return ToolScan(Tool.RUFF, package, None, (), ())
    visited = frozenset({found.path.resolve()})
    loaded = load_ruff_chain(found.path, found.source.path, context, visited=visited)
    settings = (
        *extends_settings(loaded),
        *collect_settings(merge_chain(loaded.tables), RUFF_SETTINGS),
        *selection_settings(resolve_rule_selection(loaded.tables)),
    )
    return ToolScan(Tool.RUFF, package, found.source, settings, loaded.problems)


def ty_file_scan(path: Path, context: ScanContext, package: PackageFacts) -> ToolScan:
    source = ConfigSource(context.display(path), None)
    read = context.read_toml(path)
    if isinstance(read, UnreadableFile):
        return ToolScan(Tool.TY, package, source, (), (read,))
    table = read.table if isinstance(read, TomlDocument) else EMPTY_TABLE
    return ToolScan(Tool.TY, package, source, collect_settings(table, TY_SETTINGS), ())


def ty_scan_in(directory: Path, context: ScanContext, package: PackageFacts) -> ToolScan | None:
    if has_file(directory, TY_CONFIG):
        return ty_file_scan(directory.joinpath(TY_CONFIG), context, package)
    table = read_nested_table(context.pyproject_table(directory), *TY_TABLE)
    if not table:
        return None
    source = ConfigSource(context.display(directory.joinpath(PYPROJECT)), '.'.join(TY_TABLE))
    return ToolScan(Tool.TY, package, source, collect_settings(table, TY_SETTINGS), ())


def scan_ty(context: ScanContext) -> ToolScan:
    package = context.package(Tool.TY)
    scans = (ty_scan_in(directory, context, package) for directory in context.directories)
    found = next((scan for scan in scans if scan is not None), None)
    if found is None:
        return ToolScan(Tool.TY, package, None, (), ())
    return found


def read_pytest_candidate(
    context: ScanContext, directory: Path, candidate: PytestCandidate
) -> PytestConfig | None:
    path = directory.joinpath(candidate.file_name)
    label = context.display(path)
    if candidate.file_name == PYPROJECT:
        return pytest_from_toml(context.pyprojects[directory], label, candidate)
    if not path.is_file():
        return None
    if candidate.syntax == 'toml':
        return pytest_from_toml(context.read_toml(path), label, candidate)
    return pytest_from_ini(context.read_ini(path), label, candidate)


def locate_pytest_config(context: ScanContext) -> PytestConfig | None:
    configs = (
        read_pytest_candidate(context, directory, candidate)
        for directory in context.directories
        for candidate in PYTEST_CANDIDATES
    )
    return next((config for config in configs if config is not None), None)


def scan_pytest(context: ScanContext) -> ToolScan:
    package = context.package(Tool.PYTEST)
    config = locate_pytest_config(context)
    if config is None:
        return ToolScan(Tool.PYTEST, package, None, (), ())
    settings = collect_settings(config.settings, PYTEST_SETTINGS)
    return ToolScan(Tool.PYTEST, package, config.source, settings, config.problems)


def declared_names(manifest: ProjectManifest | None) -> frozenset[str]:
    if manifest is None:
        return frozenset[str]()
    return manifest.declared_distributions | frozenset(manifest.optional_dependencies)


def is_test_plugin(name: str, options: ScanOptions) -> bool:
    return name.startswith(options.test_plugin_prefix) or name in options.test_plugin_names


def list_test_plugins(context: ScanContext) -> tuple[PackageFacts, ...]:
    names = sorted(declared_names(context.manifest))
    plugins = (name for name in names if is_test_plugin(name, context.options))
    return tuple(context.package(name) for name in plugins)


def has_nox(context: ScanContext) -> bool:
    return has_file(context.root, 'noxfile.py')


def has_tox_toml(context: ScanContext) -> bool:
    return has_file(context.root, 'tox.toml')


def has_tox_ini(context: ScanContext) -> bool:
    read = context.read_ini(context.root.joinpath('tox.ini'))
    if not isinstance(read, IniDocument):
        return False
    names = read.sections
    return any(name == TOX_SECTION or name.startswith(TOX_ENVIRONMENT_PREFIX) for name in names)


def has_tox_table(context: ScanContext) -> bool:
    return bool(read_nested_table(context.pyproject_table(context.root), *TOX_TABLE))


def default_orchestrator_checks() -> Mapping[Orchestrator, Callable[[ScanContext], bool]]:
    return MappingProxyType(
        {
            Orchestrator('nox', 'noxfile.py'): has_nox,
            Orchestrator('tox', 'tox.toml'): has_tox_toml,
            Orchestrator('tox', 'tox.ini'): has_tox_ini,
            Orchestrator('tox', 'pyproject.toml [tool.tox]'): has_tox_table,
        }
    )


def scan_tests(context: ScanContext) -> SuiteFacts:
    checks = default_orchestrator_checks()
    names = sorted(DiscoveryOptions().test_directory_names)
    return SuiteFacts(
        runner=scan_pytest(context),
        plugins=list_test_plugins(context),
        orchestrators=tuple(item for item, check in checks.items() if check(context)),
        directories=tuple(name for name in names if has_directory(context.root, name)),
    )


def list_problems(context: ScanContext) -> tuple[ScanProblem, ...]:
    reads = (*context.pyprojects.values(), context.lock)
    return tuple(read for read in reads if isinstance(read, UnreadableFile))


def list_dependency_files(context: ScanContext) -> tuple[str, ...]:
    directory = context.dependency_directory
    if directory is None:
        return ()
    names = context.options.dependency_file_names
    return tuple(name for name in names if has_file(directory, name))


def dependency_directory_label(context: ScanContext) -> str | None:
    directory = context.dependency_directory
    if directory is None or directory == context.root:
        return None
    return context.display(directory)


def scan_project(
    cwd: Path,
    options: ScanOptions | None = None,
    environment: Mapping[str, str] | None = None,
) -> ProjectScan:
    chosen = ScanOptions() if options is None else options
    variables = MappingProxyType({}) if environment is None else environment
    context = open_scan_context(cwd, chosen, variables)
    has_manifest = isinstance(context.pyprojects.get(context.root), TomlDocument | UnreadableFile)
    return ProjectScan(
        root=context.root.as_posix(),
        manifest=PYPROJECT if has_manifest else None,
        dependency_files=list_dependency_files(context),
        dependency_directory=dependency_directory_label(context),
        python=scan_python(context),
        ruff=scan_ruff(context),
        ty=scan_ty(context),
        tests=scan_tests(context),
        problems=list_problems(context),
    )


def brief_session(cwd: Path, environment: Mapping[str, str]) -> str:
    scan = scan_project(cwd, ScanOptions(), environment)
    guard = GuardOptions()
    brief = RunnerBrief(guard.runner_prefix, describe_guard_rule(guard))
    return render_session_context(scan, BriefingOptions(), brief)
