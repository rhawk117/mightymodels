import re
import warnings

from ai_engineer_cli.findings import Finding, error, warning
from ai_engineer_cli.hook.events import EVERY_TOOL_CALL_EVENTS, MATCHERLESS_EVENTS
from ai_engineer_cli.hook.nodes import Group

CATCH_ALL_MATCHERS = frozenset({'', '*'})

# A matcher made only of these characters is an exact name or a list of names, not a regex.
EXACT_MATCHER = re.compile(r'[A-Za-z0-9_\- ,|]+')
NARROW_EXACT_MATCHER = re.compile(r'[A-Za-z0-9_|]+')
NARROW_EXACT_EVENTS = frozenset({'FileChanged', 'StopFailure'})

# Claude Code tests matchers with JavaScript regexes; Python `re` is only an approximation.
# These rewrites make JavaScript-only spellings that Python rejects compile.
JAVASCRIPT_TO_PYTHON = (
    (re.compile(r'\(\?<(?![=!])'), '(?P<'),
    (re.compile(r'\\k<(\w+)>'), r'(?P=\1)'),
    (re.compile(r'\[\^\]'), r'[\\s\\S]'),
    (re.compile(r'\[\]'), '(?!)'),
)

# Python errors that JavaScript accepts: identity escapes, `\u{...}` and `\x` read as literals,
# variable-width lookbehind, numeric backreferences to groups that do not exist, and repeated
# group names in other alternatives.
TOLERATED_REGEX_ERRORS = (
    'bad escape',
    'incomplete escape',
    'look-behind requires',
    'invalid group reference',
    'redefinition of group name',
)


def matcher_findings(group: Group) -> list[Finding]:
    """Rows H33, H34 and H35 for one matcher group."""
    if 'matcher' not in group.fields:
        return missing_matcher_findings(group)
    matcher = group.fields['matcher']
    if not isinstance(matcher, str):
        return []
    if group.event in MATCHERLESS_EVENTS:
        return [warning(f'{group.where}: matcher is ignored on {group.event}')]
    return invalid_regex_findings(group, matcher)


def invalid_regex_findings(group: Group, matcher: str) -> list[Finding]:
    problem = regex_problem(matcher, group.event)
    if problem is None:
        return []
    message = f'matcher {matcher!r} is not a valid regular expression ({problem})'
    return [error(f'{group.where}: {message}')]


def missing_matcher_findings(group: Group) -> list[Finding]:
    if group.event not in EVERY_TOOL_CALL_EVENTS:
        return []
    return [warning(f'{group.where}: no matcher, so this runs on every tool call')]


def regex_problem(matcher: str, event: str) -> str | None:
    exact = NARROW_EXACT_MATCHER if event in NARROW_EXACT_EVENTS else EXACT_MATCHER
    if matcher in CATCH_ALL_MATCHERS or exact.fullmatch(matcher):
        return None
    pattern = matcher
    for javascript, python in JAVASCRIPT_TO_PYTHON:
        pattern = javascript.sub(python, pattern)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            re.compile(pattern)
    except re.error as problem:
        return None if problem.msg.startswith(TOLERATED_REGEX_ERRORS) else problem.msg
    return None
