"""Publish a request model's JSON schema with every `$ref` inlined.

PEP 695 aliases and enums come out of pydantic as `{"$ref": "#/$defs/Name"}`, which a client
cannot show as a type. The published schema carries each definition in place instead, and no
`$defs`. Keys beside a `$ref` (a field's `description` or `default`) win over the definition's.
"""

from typing import Any

type Schema = dict[str, Any]

DEFS_KEY = '$defs'
REF_KEY = '$ref'
REF_PREFIX = '#/$defs/'


class RecursiveDefinitionError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f'definition {name!r} refers to itself and cannot be inlined')
        self.name = name


def inline_refs(schema: Schema) -> Schema:
    definitions: Schema = schema.get(DEFS_KEY, {})
    body = {key: value for key, value in schema.items() if key != DEFS_KEY}
    return resolve(body, definitions, ())


def resolve(node: Any, definitions: Schema, active: tuple[str, ...]) -> Any:
    if isinstance(node, list):
        return [resolve(item, definitions, active) for item in node]
    if not isinstance(node, dict):
        return node
    if REF_KEY not in node:
        return {key: resolve(value, definitions, active) for key, value in node.items()}
    name = node[REF_KEY].removeprefix(REF_PREFIX)
    if name in active:
        raise RecursiveDefinitionError(name)
    target = resolve(definitions[name], definitions, (*active, name))
    siblings = {
        key: resolve(value, definitions, active) for key, value in node.items() if key != REF_KEY
    }
    return {**target, **siblings}
