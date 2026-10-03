import re

from ai_engineer_cli.findings import Finding, error, warning
from ai_engineer_cli.frontmatter import SkillText

ALWAYS_ON_GLOBS = frozenset({'**', '**/*'})
ROOT_ONLY_GLOB = re.compile(r'^\*\.[A-Za-z0-9]+$')
MAX_EXPANDED_PATTERNS = 1000


def check_frontmatter(rule: SkillText) -> list[Finding]:
    """Frontmatter checks for a rule file; `paths` is the only field Claude Code reads."""
    if rule.yaml_problem is not None:
        return [error(f'frontmatter is not valid YAML ({rule.yaml_problem})')]
    if not rule.fields or 'paths' not in rule.fields:
        return []
    return check_paths(paths_of(rule.fields['paths']))


def paths_of(value: object) -> list[str]:
    """The patterns of a `paths` value: a YAML list, or a comma-separated string."""
    if value is None:
        return []
    items = value if isinstance(value, list) else split_top_level(str(value))
    return [text for item in items if (text := str(item).strip())]


def split_top_level(text: str) -> list[str]:
    """Split on commas that sit outside a brace group; a backslash escapes the next character."""
    parts: list[str] = []
    depth = 0
    start = 0
    position = 0
    while position < len(text):
        char = text[position]
        if char == '\\':
            position += 1
        elif char == '{':
            depth += 1
        elif char == '}':
            depth = max(depth - 1, 0)
        elif char == ',' and depth == 0:
            parts.append(text[start:position])
            start = position + 1
        position += 1
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
    position = 0
    while position < len(pattern):
        char = pattern[position]
        if char == '\\':
            position += 2
        elif char == '[':
            end = bracket_end(pattern, position)
            if end is None:
                return True
            position = end + 1
        else:
            position += 1
    return False


def bracket_end(pattern: str, start: int) -> int | None:
    """The index of the `]` closing the bracket expression at start, or None."""
    body_start = start + 1
    if pattern[body_start : body_start + 1] in {'!', '^'}:
        body_start += 1
    # A `]` first in the expression is a member, so the search for the closing one starts after it.
    end = pattern.find(']', body_start + 1)
    return end if end != -1 else None


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
    """How many patterns the brace groups of one pattern expand to; 1 without a group."""
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
    depth = 0
    position = start
    while position < len(pattern):
        char = pattern[position]
        if char == '\\':
            position += 1
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return position
        position += 1
    return None
