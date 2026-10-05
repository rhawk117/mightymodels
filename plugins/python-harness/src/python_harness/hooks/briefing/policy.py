"""Pure scan rules: declarations, uv workspace membership, pytest's config files."""

from pathlib import PurePosixPath
from types import MappingProxyType

from python_harness.core.toml import EMPTY_TABLE, read_nested_table, read_strings, read_table
from python_harness.hooks.briefing.domain import (
    ConfigSource,
    ConfigTable,
    ConflictingPytestTables,
    Declaration,
    IniRead,
    PytestCandidate,
    PytestConfig,
    ScanProblem,
    TomlRead,
)
from python_harness.survey.domain import PYPROJECT, ProjectManifest

INI_OPTIONS = 'ini_options'
PYTEST_CANDIDATES = (
    PytestCandidate('pytest.toml', 'pytest', 'toml', matches_when_empty=True),
    PytestCandidate('.pytest.toml', 'pytest', 'toml', matches_when_empty=True),
    PytestCandidate('pytest.ini', 'pytest', 'ini', matches_when_empty=True),
    PytestCandidate('.pytest.ini', 'pytest', 'ini', matches_when_empty=True),
    PytestCandidate(PYPROJECT, 'tool.pytest', 'toml', matches_when_empty=False),
    PytestCandidate('tox.ini', 'pytest', 'ini', matches_when_empty=False),
    PytestCandidate('setup.cfg', 'tool:pytest', 'ini', matches_when_empty=False),
)


def classify_declaration(manifest: ProjectManifest, name: str) -> Declaration:
    groups = (
        (Declaration.RUNTIME, manifest.dependencies),
        (Declaration.DEVELOPMENT, manifest.dev_dependencies),
        (Declaration.OPTIONAL, manifest.optional_dependencies),
    )
    found = (declaration for declaration, names in groups if name in names)
    return next(found, Declaration.UNDECLARED)


def is_workspace_member(workspace: ConfigTable, relative: PurePosixPath) -> bool:
    members = read_strings(workspace, 'members')
    excluded = read_strings(workspace, 'exclude')
    included = any(relative.full_match(pattern) for pattern in members)
    return included and not any(relative.full_match(pattern) for pattern in excluded)


def unreadable_pytest(
    problems: tuple[ScanProblem, ...], label: str, candidate: PytestCandidate
) -> PytestConfig | None:
    if not candidate.matches_when_empty:
        return None
    return PytestConfig(ConfigSource(label, candidate.section), EMPTY_TABLE, problems)


def ini_options_config(table: ConfigTable, label: str, candidate: PytestCandidate) -> PytestConfig:
    source = ConfigSource(label, f'{candidate.section}.{INI_OPTIONS}')
    native = tuple(key for key in table if key != INI_OPTIONS)
    problems = (ConflictingPytestTables(label),) if native else ()
    return PytestConfig(source, read_table(table, INI_OPTIONS), problems)


def pytest_from_table(
    table: ConfigTable, label: str, candidate: PytestCandidate
) -> PytestConfig | None:
    if read_table(table, INI_OPTIONS):
        return ini_options_config(table, label, candidate)
    if not table and not candidate.matches_when_empty:
        return None
    return PytestConfig(ConfigSource(label, candidate.section), table, ())


def pytest_from_toml(read: TomlRead, label: str, candidate: PytestCandidate) -> PytestConfig | None:
    if read.problems:
        return unreadable_pytest(read.problems, label, candidate)
    if not read.found:
        return None
    table = read_nested_table(read.table, *candidate.section.split('.'))
    return pytest_from_table(table, label, candidate)


def pytest_from_ini(read: IniRead, label: str, candidate: PytestCandidate) -> PytestConfig | None:
    if read.problems:
        return unreadable_pytest(read.problems, label, candidate)
    if not read.found:
        return None
    section = read.sections.get(candidate.section)
    if section is None and not candidate.matches_when_empty:
        return None
    settings = EMPTY_TABLE if section is None else MappingProxyType(dict(section))
    return PytestConfig(ConfigSource(label, candidate.section), settings, ())
