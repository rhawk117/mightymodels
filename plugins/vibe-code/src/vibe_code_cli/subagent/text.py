import json
import re
from dataclasses import dataclass

from vibe_code_cli.frontmatter import parse_skill_text, split_frontmatter

UNQUOTED_DESCRIPTION = re.compile(r'^description:[ \t]*(?P<value>[^\s"\'>|].*)$', re.MULTILINE)


@dataclass(frozen=True, kw_only=True)
class AgentText:
    """fields is None when the frontmatter is not a mapping or does not parse (yaml_problem)."""

    has_block: bool
    fields: dict[str, object] | None
    yaml_problem: str | None
    body: str
    unquoted_colon: bool = False


def parse_agent_text(text: str) -> AgentText:
    raw, body = split_frontmatter(text)
    if raw is None:
        return AgentText(has_block=False, fields=None, yaml_problem=None, body=text)
    skill = parse_skill_text(text)
    unquoted = UNQUOTED_DESCRIPTION.search(raw)
    if unquoted is None:
        return AgentText(
            has_block=True, fields=skill.fields, yaml_problem=skill.yaml_problem, body=body
        )
    if skill.yaml_problem is not None and ':' in unquoted['value']:
        # The built-in reads this description but PyYAML rejects it, so the checks get it quoted.
        skill = parse_skill_text(f'---\n{quote_description(raw)}---\n{body}')
        return AgentText(
            has_block=True,
            fields=skill.fields,
            yaml_problem=skill.yaml_problem,
            body=body,
            unquoted_colon=True,
        )
    description = (skill.fields or {}).get('description')
    has_colon = isinstance(description, str) and ':' in description
    return AgentText(
        has_block=True,
        fields=skill.fields,
        yaml_problem=skill.yaml_problem,
        body=body,
        unquoted_colon=has_colon,
    )


def quote_description(raw: str) -> str:
    return UNQUOTED_DESCRIPTION.sub(
        lambda match: f'description: {json.dumps(match["value"])}', raw, count=1
    )
