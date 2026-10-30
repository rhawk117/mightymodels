import re
from typing import Any

import pytest
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.published_schema import RecursiveDefinitionError, inline_refs

TYPE_KEYS = ('type', 'enum', 'const')
USE_SENTENCE = re.compile(r'\bUse\s')


def states_type(node: dict[str, Any]) -> bool:
    if any(key in node for key in TYPE_KEYS):
        return True
    branches = node.get('anyOf')
    return bool(branches) and all(states_type(branch) for branch in branches)


def has_ref(node: object) -> bool:
    if isinstance(node, dict):
        return '$ref' in node or any(has_ref(value) for value in node.values())
    if isinstance(node, list):
        return any(has_ref(item) for item in node)
    return False


def published_properties() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (tool.name, name, prop)
        for tool in create_catalog().list_tools()
        for name, prop in tool.parameters.get('properties', {}).items()
    ]


def is_described(prop: object) -> bool:
    return isinstance(prop, dict) and bool(str(prop.get('description', '')).strip())


def undescribed_properties(node: object, path: str) -> list[str]:
    if isinstance(node, list):
        children = [(f'{path}[{index}]', item) for index, item in enumerate(node)]
        return [gap for child, item in children for gap in undescribed_properties(item, child)]
    if not isinstance(node, dict):
        return []
    properties = node.get('properties')
    own = (
        [f'{path}.{name}' for name, prop in properties.items() if not is_described(prop)]
        if isinstance(properties, dict)
        else []
    )
    nested = [
        gap for key, value in node.items() for gap in undescribed_properties(value, f'{path}.{key}')
    ]
    return own + nested


class TestPublishedSchemas:
    @pytest.mark.parametrize(('tool', 'name', 'prop'), published_properties())
    def test_property_states_its_type(self, tool: str, name: str, prop: dict[str, Any]) -> None:
        assert states_type(prop), f'{tool}.{name}'

    def test_every_property_states_a_description(self) -> None:
        missing = [
            gap
            for tool in create_catalog().list_tools()
            for gap in undescribed_properties(tool.parameters, tool.name)
        ]
        assert missing == []

    def test_no_published_schema_holds_a_ref_or_defs(self) -> None:
        for tool in create_catalog().list_tools():
            assert not has_ref(tool.parameters), tool.name
            assert '$defs' not in tool.parameters, tool.name


DEFS = {
    'Text': {'type': 'string', 'maxLength': 5},
    'Pair': {'type': 'object', 'properties': {'a': {'$ref': '#/$defs/Text'}}},
}


class TestInlineRefs:
    def test_siblings_win_over_the_definition(self) -> None:
        schema = {
            '$defs': DEFS,
            'properties': {'x': {'$ref': '#/$defs/Text', 'default': '', 'maxLength': 9}},
        }
        assert inline_refs(schema) == {
            'properties': {'x': {'type': 'string', 'maxLength': 9, 'default': ''}}
        }

    def test_refs_nested_in_unions_items_and_definitions_are_inlined(self) -> None:
        schema = {
            '$defs': DEFS,
            'properties': {
                'opt': {'anyOf': [{'$ref': '#/$defs/Text'}, {'type': 'null'}], 'default': None},
                'many': {'type': 'array', 'items': {'$ref': '#/$defs/Pair'}},
            },
        }
        properties = inline_refs(schema)['properties']
        assert properties['opt'] == {
            'anyOf': [{'type': 'string', 'maxLength': 5}, {'type': 'null'}],
            'default': None,
        }
        assert properties['many']['items']['properties']['a'] == {'type': 'string', 'maxLength': 5}

    def test_recursive_definition_is_refused(self) -> None:
        schema = {
            '$defs': {'Node': {'properties': {'next': {'$ref': '#/$defs/Node'}}}},
            'properties': {'n': {'$ref': '#/$defs/Node'}},
        }
        with pytest.raises(RecursiveDefinitionError):
            inline_refs(schema)


class TestToolDescriptions:
    def test_every_description_says_when_to_use_the_tool(self) -> None:
        missing = [
            tool.name
            for tool in create_catalog().list_tools()
            if not USE_SENTENCE.search(tool.description or '')
        ]
        assert missing == []

    def test_every_description_fits_the_context_budget(self) -> None:
        long = [
            tool.name for tool in create_catalog().list_tools() if len(tool.description or '') > 300
        ]
        assert long == []
