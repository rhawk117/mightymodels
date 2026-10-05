"""Tool settings from parsed config tables, with ruff's `extend` chain resolved like ruff.

Keys merge child over parent. A file that sets `select` starts the rule selection over,
keeping only ignores from an empty parent `select`; otherwise its `extend-select`
re-enables the parent's ignored codes it covers, and both lists add up.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial, reduce
from types import MappingProxyType

from python_harness.core.toml import (
    EMPTY_TABLE,
    is_table,
    normalize_name,
    read_items,
    read_nested_table,
)
from python_harness.hooks.briefing.domain import ConfigTable, Setting

ALL_RULES = 'ALL'
VARIABLE = re.compile(r'\$\{(\w+)\}|\$(\w+)')
VERSION_TEXT = re.compile(r'[0-9A-Za-z.+!_-]{1,64}')


@dataclass(frozen=True, slots=True)
class SettingSpec:
    name: str
    paths: tuple[tuple[str, ...], ...]


def setting_spec(name: str, *paths: tuple[str, ...]) -> SettingSpec:
    return SettingSpec(name, paths or ((name,),))


RUFF_SETTINGS = (
    setting_spec('target-version'),
    setting_spec('line-length'),
    setting_spec('quote-style', ('format', 'quote-style')),
    setting_spec('preview', ('lint', 'preview'), ('preview',)),
    setting_spec('docstring convention', ('lint', 'pydocstyle', 'convention')),
    setting_spec('pylint', ('lint', 'pylint')),
    setting_spec('mccabe', ('lint', 'mccabe')),
)
SELECT = setting_spec('select', ('lint', 'select'), ('select',))
EXTEND_SELECT = setting_spec('extend-select', ('lint', 'extend-select'), ('extend-select',))
IGNORE = setting_spec('ignore', ('lint', 'ignore'), ('ignore',))
EXTEND_IGNORE = setting_spec('extend-ignore', ('lint', 'extend-ignore'), ('extend-ignore',))
TY_SETTINGS = (
    setting_spec('python-version', ('environment', 'python-version')),
    setting_spec('python-platform', ('environment', 'python-platform')),
    setting_spec('error-on-warning', ('terminal', 'error-on-warning')),
    setting_spec('rules', ('rules',)),
    setting_spec('src include', ('src', 'include')),
    setting_spec('src exclude', ('src', 'exclude')),
)
PYTEST_SETTINGS = tuple(
    setting_spec(name)
    for name in (
        'minversion',
        'testpaths',
        'addopts',
        'pythonpath',
        'python_files',
        'asyncio_mode',
        'xfail_strict',
        'required_plugins',
    )
)


@dataclass(frozen=True, slots=True)
class RuleSelection:
    select: tuple[str, ...] | None
    extend_select: tuple[str, ...]
    ignore: tuple[str, ...]


EMPTY_SELECTION = RuleSelection(None, (), ())


def lookup_setting(table: ConfigTable, path: tuple[str, ...]) -> object:
    *parents, last = path
    return read_nested_table(table, *parents).get(last)


def first_value(table: ConfigTable, setting: SettingSpec) -> object:
    values = (lookup_setting(table, path) for path in setting.paths)
    return next((value for value in values if value is not None), None)


def collect_settings(table: ConfigTable, specs: Iterable[SettingSpec]) -> tuple[Setting, ...]:
    values = ((item.name, first_value(table, item)) for item in specs)
    return tuple(Setting(name, value) for name, value in values if value is not None)


def merge_value(base: object, child: object) -> object:
    if child is None:
        return base
    if is_table(base) and is_table(child):
        return merge_tables(base, child)
    return child


def merge_tables(base: ConfigTable, child: ConfigTable) -> ConfigTable:
    keys = (*base, *(key for key in child if key not in base))
    merged = {key: merge_value(base.get(key), child.get(key)) for key in keys}
    return MappingProxyType(merged)


def merge_chain(tables: Sequence[ConfigTable]) -> ConfigTable:
    return reduce(merge_tables, reversed(tables), EMPTY_TABLE)


def strings_of(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def rule_selection_of(table: ConfigTable) -> RuleSelection:
    select = first_value(table, SELECT)
    ignored = (first_value(table, IGNORE), first_value(table, EXTEND_IGNORE))
    return RuleSelection(
        select=None if select is None else strings_of(select),
        extend_select=strings_of(first_value(table, EXTEND_SELECT)),
        ignore=tuple(code for value in ignored for code in strings_of(value)),
    )


def re_enables(selector: str, code: str) -> bool:
    return selector == ALL_RULES or code.startswith(selector)


def fold_selection(parent: RuleSelection, child: RuleSelection) -> RuleSelection:
    if child.select is not None:
        carried = parent.ignore if parent.select == () else ()
        return RuleSelection(child.select, child.extend_select, (*carried, *child.ignore))
    kept = tuple(
        code
        for code in parent.ignore
        if not any(re_enables(selector, code) for selector in child.extend_select)
    )
    return RuleSelection(
        select=parent.select,
        extend_select=(*parent.extend_select, *child.extend_select),
        ignore=(*kept, *child.ignore),
    )


def resolve_rule_selection(tables: Sequence[ConfigTable]) -> RuleSelection:
    selections = (rule_selection_of(table) for table in reversed(tables))
    return reduce(fold_selection, selections, EMPTY_SELECTION)


def selection_settings(selection: RuleSelection) -> tuple[Setting, ...]:
    lists = (
        ('select', selection.select),
        ('extend-select', selection.extend_select or None),
        ('ignore', selection.ignore or None),
    )
    return tuple(Setting(name, list(codes)) for name, codes in lists if codes is not None)


def substitute_variable(found: re.Match[str], environment: Mapping[str, str]) -> str:
    name = found.group(1) or found.group(2)
    return environment.get(name, found.group(0))


def expand_variables(text: str, environment: Mapping[str, str]) -> str:
    return VARIABLE.sub(partial(substitute_variable, environment=environment), text)


def locked_version_of(entry: object) -> tuple[str, str] | None:
    if not isinstance(entry, Mapping):
        return None
    name = entry.get('name')
    version = entry.get('version')
    if not isinstance(name, str) or not isinstance(version, str):
        return None
    if VERSION_TEXT.fullmatch(version) is None:
        return None
    return normalize_name(name), version


def parse_locked_versions(lock: ConfigTable) -> Mapping[str, str]:
    pairs = (locked_version_of(entry) for entry in read_items(lock, 'package'))
    return MappingProxyType(dict(pair for pair in pairs if pair is not None))
