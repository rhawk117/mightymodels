import re
from dataclasses import dataclass

import yaml
from yaml.resolver import BaseResolver

YAML_BOOL = 'tag:yaml.org,2002:bool'


class FrontmatterLoader(yaml.SafeLoader):
    """Read safe YAML; record bad keys, and keep YAML 1.1 bool aliases as strings."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self.key_problems: list[str] = []


FrontmatterLoader.yaml_implicit_resolvers = {
    char: [(tag, pattern) for tag, pattern in resolvers if tag != YAML_BOOL]
    for char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
FrontmatterLoader.add_implicit_resolver(
    YAML_BOOL, re.compile(r'^(?:true|false)$', re.IGNORECASE), list('tTfF')
)


def checked_mapping(
    loader: FrontmatterLoader,
    node: yaml.nodes.MappingNode,
    *,
    deep: bool = False,
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        line = key_node.start_mark.line + 2
        if not isinstance(key, str):
            loader.key_problems.append(f'frontmatter key {key!r} on line {line} is not a string')
            continue
        if key in result:
            loader.key_problems.append(f'duplicate frontmatter key {key!r} on line {line}')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


FrontmatterLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, checked_mapping)


@dataclass(frozen=True)
class SkillText:
    """fields is None when the file has no frontmatter block or it is not a YAML mapping."""

    fields: dict[str, object] | None
    key_problems: list[str]
    body: str
    yaml_problem: str | None = None


def split_frontmatter(text: str) -> tuple[str | None, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != '---':
        return None, text
    closing = next(
        (index for index, line in enumerate(lines[1:], 1) if line.strip() == '---'), None
    )
    if closing is None:
        return None, text
    return ''.join(lines[1:closing]), ''.join(lines[closing + 1 :])


def parse_skill_text(text: str) -> SkillText:
    raw, body = split_frontmatter(text)
    if raw is None:
        return SkillText(None, [], body)
    loader = FrontmatterLoader(raw)
    try:
        fields = loader.get_single_data()
    except yaml.YAMLError as problem:
        first_line = (str(problem).splitlines() or [type(problem).__name__])[0]
        return SkillText(None, [], body, first_line)
    finally:
        loader.dispose()
    if fields is None:
        fields = {}
    if not isinstance(fields, dict):
        return SkillText(None, [], body)
    return SkillText(fields, loader.key_problems, body)
