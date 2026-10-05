"""Toolchain facts a session starts with: interpreter pin, ruff, ty and the test suite."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum, auto
from types import MappingProxyType
from typing import Literal, Self

MEBIBYTE = 1024 * 1024

type IniSections = Mapping[str, Mapping[str, str]]
type ConfigTable = Mapping[str, object]

EMPTY_TABLE: ConfigTable = MappingProxyType({})
EMPTY_SECTIONS: IniSections = MappingProxyType[str, Mapping[str, str]]({})


class Tool(StrEnum):
    RUFF = 'ruff'
    TY = 'ty'
    PYTEST = 'pytest'


class Declaration(StrEnum):
    RUNTIME = auto()
    DEVELOPMENT = auto()
    OPTIONAL = auto()
    UNDECLARED = auto()


@dataclass(frozen=True, slots=True)
class PackageFacts:
    name: str
    declaration: Declaration
    locked_version: str | None


@dataclass(frozen=True, slots=True)
class ConfigSource:
    path: str
    table: str | None


@dataclass(frozen=True, slots=True)
class Setting:
    name: str
    value: object


@dataclass(frozen=True, slots=True)
class MissingFile:
    kind: Literal['missing'] = field(default='missing', init=False)

    @property
    def text(self) -> str:
        return ''

    @property
    def table(self) -> ConfigTable:
        return EMPTY_TABLE

    @property
    def sections(self) -> IniSections:
        return EMPTY_SECTIONS

    @property
    def problems(self) -> tuple[()]:
        return ()

    @property
    def found(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class UnreadableFile:
    label: str
    reason: str
    kind: Literal['unreadable'] = field(default='unreadable', init=False)

    @property
    def text(self) -> str:
        return ''

    @property
    def table(self) -> ConfigTable:
        return EMPTY_TABLE

    @property
    def sections(self) -> IniSections:
        return EMPTY_SECTIONS

    @property
    def problems(self) -> tuple[Self]:
        return (self,)

    @property
    def found(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class TextFile:
    text: str
    kind: Literal['text'] = field(default='text', init=False)

    @property
    def table(self) -> ConfigTable:
        return EMPTY_TABLE

    @property
    def sections(self) -> IniSections:
        return EMPTY_SECTIONS

    @property
    def problems(self) -> tuple[()]:
        return ()

    @property
    def found(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class TomlDocument:
    table: ConfigTable
    kind: Literal['toml'] = field(default='toml', init=False)

    @property
    def text(self) -> str:
        return ''

    @property
    def sections(self) -> IniSections:
        return EMPTY_SECTIONS

    @property
    def problems(self) -> tuple[()]:
        return ()

    @property
    def found(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class IniDocument:
    sections: IniSections
    kind: Literal['ini'] = field(default='ini', init=False)

    @property
    def text(self) -> str:
        return ''

    @property
    def table(self) -> ConfigTable:
        return EMPTY_TABLE

    @property
    def problems(self) -> tuple[()]:
        return ()

    @property
    def found(self) -> bool:
        return True


type TextRead = TextFile | MissingFile | UnreadableFile
type TomlRead = TomlDocument | MissingFile | UnreadableFile
type IniRead = IniDocument | MissingFile | UnreadableFile


@dataclass(frozen=True, slots=True)
class ExtendCycle:
    path: str
    kind: Literal['extend_cycle'] = field(default='extend_cycle', init=False)


@dataclass(frozen=True, slots=True)
class ExtendChainTooLong:
    limit: int
    kind: Literal['extend_chain_too_long'] = field(default='extend_chain_too_long', init=False)


@dataclass(frozen=True, slots=True)
class ExtendTargetMissing:
    path: str
    kind: Literal['extend_target_missing'] = field(default='extend_target_missing', init=False)


@dataclass(frozen=True, slots=True)
class ExtendTargetOutside:
    path: str
    kind: Literal['extend_target_outside'] = field(default='extend_target_outside', init=False)


@dataclass(frozen=True, slots=True)
class ConflictingPytestTables:
    path: str
    kind: Literal['conflicting_pytest_tables'] = field(
        default='conflicting_pytest_tables', init=False
    )


type ScanProblem = (
    UnreadableFile
    | ExtendCycle
    | ExtendChainTooLong
    | ExtendTargetMissing
    | ExtendTargetOutside
    | ConflictingPytestTables
)


@dataclass(frozen=True, slots=True)
class PytestCandidate:
    file_name: str
    section: str
    syntax: Literal['toml', 'ini']
    matches_when_empty: bool


@dataclass(frozen=True, slots=True)
class PytestConfig:
    source: ConfigSource
    settings: ConfigTable
    problems: tuple[ScanProblem, ...]


@dataclass(frozen=True, slots=True)
class ToolScan:
    tool: Tool
    package: PackageFacts
    config: ConfigSource | None
    settings: tuple[Setting, ...]
    problems: tuple[ScanProblem, ...]


@dataclass(frozen=True, slots=True)
class VirtualEnvironment:
    path: str
    version: str | None
    implementation: str | None


@dataclass(frozen=True, slots=True)
class PythonPin:
    version: str
    path: str


@dataclass(frozen=True, slots=True)
class PythonFacts:
    pin: PythonPin | None
    requires_python: str | None
    environment: VirtualEnvironment | None


@dataclass(frozen=True, slots=True)
class Orchestrator:
    name: str
    source: str


@dataclass(frozen=True, slots=True)
class SuiteFacts:
    runner: ToolScan
    plugins: tuple[PackageFacts, ...]
    orchestrators: tuple[Orchestrator, ...]
    directories: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectScan:
    root: str
    manifest: str | None
    dependency_files: tuple[str, ...]
    dependency_directory: str | None
    python: PythonFacts
    ruff: ToolScan
    ty: ToolScan
    tests: SuiteFacts
    problems: tuple[ScanProblem, ...]

    @property
    def has_python_markers(self) -> bool:
        python = self.python
        configs = (self.ruff.config, self.ty.config, self.tests.runner.config)
        markers = (self.manifest, python.pin, python.environment, *configs)
        return bool(self.dependency_files) or any(item is not None for item in markers)


@dataclass(frozen=True, slots=True)
class ScanOptions:
    dependency_file_names: tuple[str, ...] = (
        'uv.lock',
        'poetry.lock',
        'pdm.lock',
        'pixi.lock',
        'Pipfile.lock',
        'requirements.txt',
    )
    version_file_name: str = '.python-version'
    environment_name: str = '.venv'
    test_plugin_names: frozenset[str] = frozenset({'coverage', 'hypothesis'})
    test_plugin_prefix: str = 'pytest-'
    max_file_bytes: int = 16 * MEBIBYTE
    max_extend_depth: int = 8


@dataclass(frozen=True, slots=True)
class BriefingOptions:
    list_limit: int = 12
    value_limit: int = 240
    context_limit: int = 9000


@dataclass(frozen=True, slots=True)
class RunnerBrief:
    prefix: str
    rule: str
