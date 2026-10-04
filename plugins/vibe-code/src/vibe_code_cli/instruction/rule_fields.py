import re
from itertools import accumulate

import msgspec
from msgspec import UNSET, UnsetType

from vibe_code_cli.findings import Finding, error, warning
from vibe_code_cli.frontmatter import SkillText

ALWAYS_ON_GLOBS = frozenset({'**', '**/*'})
ROOT_ONLY_GLOB = re.compile(r'^\*\.[A-Za-z0-9]+$')
MAX_EXPANDED_PATTERNS = 1000
BRACE_TOKEN = re.compile(r'\\.|[{},]', re.DOTALL)
BRACKET_TOKEN = re.compile(r'\\.|\[[!^]?+.[^\]]*\]|(?P<invalid>\[)', re.DOTALL)


class RuleFrontmatter(msgspec.Struct, frozen=True, kw_only=True):
    paths: str | list[str] | UnsetType | None = UNSET


def check_frontmatter(rule: SkillText) -> list[Finding]:
    if rule.yaml_problem is not None:
        return [error(f'frontmatter is not valid YAML ({rule.yaml_problem})')]
    findings: list[Finding] = [error(rule.key_problem)] if rule.key_problem else []
    if not rule.fields:
        return findings
    try:
        frontmatter = msgspec.convert(rule.fields, RuleFrontmatter)
    except msgspec.ValidationError as problem:
        return [*findings, error(str(problem))]
    return [*findings, *check_rule_paths(frontmatter.paths)]


def check_rule_paths(paths: str | list[str] | UnsetType | None) -> list[Finding]:
    if isinstance(paths, UnsetType):
        return []
    return check_paths(paths_of(paths))


def paths_of(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else split_top_level(value)
    return [text for item in items if (text := item.strip())]


def split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for token in BRACE_TOKEN.finditer(text):
        char = token[0]
        depth = max(depth + (char == '{') - (char == '}'), 0)
        if char == ',' and depth == 0:
            parts.append(text[start : token.start()])
            start = token.end()
    parts.append(text[start:])
    return parts


def check_paths(patterns: list[str]) -> list[Finding]:
    if not patterns:
        return [error('paths is empty; omit the key for a rule that always loads')]
    findings = [finding for pattern in patterns if (finding := check_glob(pattern))]
    findings.extend(check_brackets(patterns))
    findings.extend(check_brace_budget(patterns))
    return findings


def check_glob(pattern: str) -> Finding | None:
    if pattern in ALWAYS_ON_GLOBS:
        return warning(
            f"paths '{pattern}' matches every file, so the rule loads on any file read; "
            'omit paths for an always-on rule, or keep short always-on text in CLAUDE.md'
        )
    if ROOT_ONLY_GLOB.match(pattern):
        return warning(
            f"paths '{pattern}' matches only the project root; '**/{pattern}' matches at any depth"
        )
    if pattern.startswith('/'):
        return warning(f"paths '{pattern}' starts with '/'; globs are project-relative")
    return None


def check_brackets(patterns: list[str]) -> list[Finding]:
    return [
        warning(
            f"paths '{pattern}' has a '[' that is not a valid bracket expression, "
            "so it matches nothing; escape a literal one as '\\['"
        )
        for pattern in patterns
        if has_invalid_bracket(pattern)
    ]


def has_invalid_bracket(pattern: str) -> bool:
    return any(token['invalid'] for token in BRACKET_TOKEN.finditer(pattern))


def check_brace_budget(patterns: list[str]) -> list[Finding]:
    expanded = sum(expanded_count(pattern) for pattern in patterns if '{' in pattern)
    if expanded <= MAX_EXPANDED_PATTERNS:
        return []
    return [
        error(
            f'paths expands to {expanded} patterns, over the budget of {MAX_EXPANDED_PATTERNS}; '
            'Claude Code then uses the patterns unexpanded and their literal braces match no files'
        )
    ]


def expanded_count(pattern: str) -> int:
    total = 1
    position = 0
    while position < len(pattern):
        char = pattern[position]
        end = matching_brace(pattern, position) if char == '{' else None
        if end is None:
            position += 2 if char == '\\' else 1
            continue
        alternatives = split_top_level(pattern[position + 1 : end])
        total *= sum(expanded_count(alternative) for alternative in alternatives)
        position = end + 1
    return total


def matching_brace(pattern: str, start: int) -> int | None:
    tokens = list(BRACE_TOKEN.finditer(pattern, start))
    depths = accumulate((token[0] == '{') - (token[0] == '}') for token in tokens)
    token_depths = zip(tokens, depths, strict=True)
    closing = (token.start() for token, depth in token_depths if depth == 0 and token[0] == '}')
    return next(closing, None)
