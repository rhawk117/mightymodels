import ast
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Literal

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from _pytest.mark import ParameterSet

type AsyncRule = Literal['unit-in-async', 'asyncio-lock', 'threading', 'gather']

SOURCE_ROOT = Path(str(files('mightymodels_mcp')))
UNIT_METHODS = frozenset({'read', 'write'})
THREADING_MODULE = 'threading'


@dataclass(slots=True, kw_only=True, frozen=True)
class AsyncRuleViolation:
    rule: AsyncRule
    line: int


def opens_a_unit(item: ast.withitem) -> bool:
    call = item.context_expr
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in UNIT_METHODS
    )


def find_units_in_async(tree: ast.Module) -> Iterator[AsyncRuleViolation]:
    async_functions = (node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef))
    for function in async_functions:
        blocks = (node for node in ast.walk(function) if isinstance(node, ast.With | ast.AsyncWith))
        yield from (
            AsyncRuleViolation(rule='unit-in-async', line=block.lineno)
            for block in blocks
            if any(map(opens_a_unit, block.items))
        )


def imported_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name for alias in node.names}

    if isinstance(node, ast.ImportFrom):
        module = node.module or ''
        return {module} | {f'{module}.{alias.name}' for alias in node.names}

    return set()


def find_concurrency_rule(node: ast.AST) -> AsyncRule | None:
    names = imported_names(node)
    if any(name.split('.')[0] == THREADING_MODULE for name in names):
        return 'threading'

    if 'asyncio.Lock' in names:
        return 'asyncio-lock'

    is_lock_attribute = (
        isinstance(node, ast.Attribute)
        and node.attr == 'Lock'
        and isinstance(node.value, ast.Name)
        and node.value.id == 'asyncio'
    )
    if is_lock_attribute:
        return 'asyncio-lock'

    is_gather = (isinstance(node, ast.Attribute) and node.attr == 'gather') or (
        isinstance(node, ast.Name) and node.id == 'gather'
    )
    if is_gather or any(name.endswith('.gather') for name in names):
        return 'gather'

    return None


def find_concurrency(tree: ast.Module) -> Iterator[AsyncRuleViolation]:
    located = (node for node in ast.walk(tree) if isinstance(node, ast.stmt | ast.expr))
    for node in located:
        if rule := find_concurrency_rule(node):
            yield AsyncRuleViolation(rule=rule, line=node.lineno)


def find_violations(source: str) -> list[AsyncRuleViolation]:
    tree = ast.parse(source)
    return [*find_units_in_async(tree), *find_concurrency(tree)]


@dataclass(slots=True, kw_only=True, frozen=True)
class RuleSample:
    name: str
    source: str
    rule: AsyncRule

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def refused_sample_cases() -> pytest.MarkDecorator:
    samples = [
        RuleSample(
            name='with-read-in-async',
            source='async def load(db):\n    with db.read() as unit:\n        return unit\n',
            rule='unit-in-async',
        ),
        RuleSample(
            name='async-with-write-in-async',
            source='async def save(db):\n    async with db.write() as unit:\n        return unit\n',
            rule='unit-in-async',
        ),
        RuleSample(
            name='asyncio-lock-attribute',
            source='import asyncio\nLOCK = asyncio.Lock()\n',
            rule='asyncio-lock',
        ),
        RuleSample(
            name='asyncio-lock-import',
            source='from asyncio import Lock\n',
            rule='asyncio-lock',
        ),
        RuleSample(name='threading-import', source='import threading\n', rule='threading'),
        RuleSample(
            name='threading-from-import',
            source='from threading import Thread\n',
            rule='threading',
        ),
        RuleSample(
            name='gather-call',
            source='import asyncio\nasync def run(a, b):\n    await asyncio.gather(a, b)\n',
            rule='gather',
        ),
        RuleSample(name='gather-import', source='from asyncio import gather\n', rule='gather'),
    ]
    return pytest.mark.parametrize('sample', [sample.param for sample in samples])


def source_file_cases() -> pytest.MarkDecorator:
    sources = sorted(SOURCE_ROOT.rglob('*.py'))
    return pytest.mark.parametrize(
        'source_path',
        [pytest.param(path, id=str(path.relative_to(SOURCE_ROOT))) for path in sources],
    )


class TestAsyncRules:
    allowed_source = dedent("""
        def load(db):
            with db.read() as unit:
                return unit


        async def run(dependencies):
            async with dependencies.state.open() as state:
                return state
    """)

    @refused_sample_cases()
    def test_sample_is_refused(self, sample: RuleSample) -> None:
        rules = {violation.rule for violation in find_violations(sample.source)}
        assert sample.rule in rules

    def test_sync_unit_and_async_state_open_are_allowed(self) -> None:
        assert find_violations(self.allowed_source) == []

    @source_file_cases()
    def test_package_source_keeps_the_async_rules(self, source_path: Path) -> None:
        assert find_violations(source_path.read_text(encoding='utf-8')) == []
