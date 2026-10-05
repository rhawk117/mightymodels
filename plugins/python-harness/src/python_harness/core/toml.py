"""Reading a parsed TOML table: a value of the wrong type reads as absent."""

import re
from collections.abc import Iterable, Iterator, Mapping
from functools import reduce
from types import MappingProxyType
from typing import TypeIs

type TomlTable = Mapping[str, object]

EMPTY_TABLE: TomlTable = MappingProxyType({})
NAME_SEPARATORS = re.compile(r'[-_.]+')


def is_table(value: object) -> TypeIs[TomlTable]:
    return isinstance(value, Mapping)


def read_table(table: TomlTable, key: str) -> TomlTable:
    value = table.get(key)
    if is_table(value):
        return value
    return EMPTY_TABLE


def read_nested_table(table: TomlTable, *keys: str) -> TomlTable:
    return reduce(read_table, keys, table)


def read_string(table: TomlTable, key: str) -> str | None:
    value = table.get(key)
    if isinstance(value, str):
        return value
    return None


def read_items(table: TomlTable, key: str) -> tuple[object, ...]:
    value = table.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(value)


def select_strings(items: Iterable[object]) -> Iterator[str]:
    return (item for item in items if isinstance(item, str))


def read_strings(table: TomlTable, key: str) -> tuple[str, ...]:
    return tuple(select_strings(read_items(table, key)))


def normalize_name(name: str) -> str:
    return NAME_SEPARATORS.sub('-', name).lower()
