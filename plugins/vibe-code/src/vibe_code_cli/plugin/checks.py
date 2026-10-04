import re
from collections.abc import Callable
from urllib.parse import urlsplit

from msgspec import UnsetType

from ai_engineer_cli.findings import Finding, error, warning
from ai_engineer_cli.plugin.kinds import KIND_SPECS, OUTSIDE_PLUGIN_KINDS, RENAMED_KINDS
from ai_engineer_cli.plugin.record import (
    AUDIENCE_HOW,
    CHANNELS,
    DECISIONS,
    PLUGIN_KINDS,
    STATUSES,
    Component,
    Dependency,
    Plan,
)

KEBAB_CASE = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
COMPONENT_NAME = re.compile(r'[a-z0-9]+(?:[-_][a-z0-9]+)*')
RESERVED_PREFIX = 'claude-'
FORBIDDEN_NAME_CHARACTERS = {
    '.': 'a dot',
    ' ': 'a space',
    '@': '@',
    ':': ':',
    '/': 'a path separator',
    '\\': 'a path separator',
}


def name_problem(name: str) -> str | None:
    """Why a plugin name fails the Claude Code rule, or None when it passes (PP-A16)."""
    for character, label in FORBIDDEN_NAME_CHARACTERS.items():
        if character in name:
            return f'name {name!r} must not contain {label}'
    if name.startswith(RESERVED_PREFIX):
        return f'name {name!r} must not start with {RESERVED_PREFIX!r}; it is reserved'
    if KEBAB_CASE.fullmatch(name) is None:
        return (
            f'name {name!r} must be non-empty kebab-case: lowercase letters and digits joined by -'
        )
    return None


def check_name(plan: Plan) -> str | None:
    return name_problem(plan.name)


def check_description(plan: Plan) -> str | None:
    if plan.description:
        return None
    return 'description is required; the plan is the record of why the plugin exists'


def check_problem(plan: Plan) -> str | None:
    if plan.problem:
        return None
    return 'problem is required; the plan is the record of why the plugin exists'


def check_audience(plan: Plan) -> str | None:
    audience = plan.audience
    if audience is not None and audience.who and audience.how in AUDIENCE_HOW:
        return None
    return f'audience needs who and how (one of {AUDIENCE_HOW})'


def check_kinds(plan: Plan) -> str | None:
    if plan.kinds and all(kind in PLUGIN_KINDS for kind in plan.kinds):
        return None
    return f'kinds must be a non-empty subset of {PLUGIN_KINDS}'


def check_ecosystem(plan: Plan) -> str | None:
    if 'ecosystem' not in plan.kinds or plan.ecosystem:
        return None
    return 'an ecosystem plugin names its ecosystem (python, typescript, terraform, ...)'


def check_distribution(plan: Plan) -> str | None:
    if plan.distribution is not None and plan.distribution.channel in CHANNELS:
        return None
    return f'distribution.channel must be one of {CHANNELS}'


def check_keywords(plan: Plan) -> str | None:
    if plan.keywords:
        return None
    return 'keywords is a non-empty list; marketplaces search it'


def check_has_components(plan: Plan) -> str | None:
    if plan.components:
        return None
    return 'at least one component; a plugin with nothing in it is a manifest'


def check_outside(plan: Plan) -> str | None:
    for item in plan.outside_plugin:
        if not (item.need or item.what) or not item.mechanism:
            return 'outside_plugin entries need a need (or what) and a mechanism'
    return None


def check_author(plan: Plan) -> str | None:
    """PP-B11: an author object that is present needs a name."""
    if plan.author is None or plan.author.name:
        return None
    return 'author needs a name'


def check_homepage(plan: Plan) -> str | None:
    """PP-B12: Claude Code fails to load a plugin whose homepage does not parse as a URL."""
    if plan.homepage is None:
        return None
    try:
        parts = urlsplit(plan.homepage)
    except ValueError:
        parts = None
    if parts is not None and parts.scheme and parts.netloc:
        return None
    return f'homepage {plan.homepage!r} must be a URL with a scheme and a host'


def check_user_config(plan: Plan) -> str | None:
    """PP-B3: each option needs the three fields Claude Code's configuration dialog shows."""
    for key, option in plan.user_config.items():
        missing = [
            field for field in ('type', 'title', 'description') if not getattr(option, field)
        ]
        if missing:
            return f'userConfig.{key} needs {", ".join(missing)}'
    return None


def check_dependencies(plan: Plan) -> str | None:
    """PP-B4: each dependency is a plugin name, `name@marketplace` or an object with a name."""
    for entry in plan.dependencies:
        name = entry.name if isinstance(entry, Dependency) else entry
        if not name.split('@')[0]:
            return 'dependencies entries must name a plugin'
    return None


PLAN_CHECKS: tuple[Callable[[Plan], str | None], ...] = (
    check_name,
    check_description,
    check_problem,
    check_audience,
    check_kinds,
    check_ecosystem,
    check_distribution,
    check_keywords,
    check_has_components,
    check_outside,
    check_author,
    check_homepage,
    check_user_config,
    check_dependencies,
)


def check_kind(component: Component) -> str | None:
    if component.kind in KIND_SPECS:
        return None
    if component.kind in OUTSIDE_PLUGIN_KINDS:
        return (
            f'kind {component.kind} is not a plugin component: '
            f'{OUTSIDE_PLUGIN_KINDS[component.kind]}'
        )
    if component.kind in RENAMED_KINDS:
        return f'kind {component.kind} is called {RENAMED_KINDS[component.kind]} for Claude Code'
    return f'kind must be one of {sorted(KIND_SPECS)}'


def check_component_name(component: Component) -> str | None:
    if COMPONENT_NAME.fullmatch(component.name):
        return None
    return 'name must be kebab-case or snake_case'


def check_purpose(component: Component) -> str | None:
    return None if component.purpose else 'purpose is required'


def check_status(component: Component) -> str | None:
    if component.status in STATUSES:
        return None
    return 'status must be planned or built'


def check_builder(component: Component) -> str | None:
    spec = KIND_SPECS.get(component.kind)
    if (
        spec is None
        or isinstance(component.builder, UnsetType)
        or component.builder == spec.builder
    ):
        return None
    return f'builder for {component.kind} is {spec.builder}'


def check_advice(component: Component) -> str | None:
    advice = component.advice
    if advice is None or (advice.mechanism and advice.reason):
        return None
    return 'advice must be null or an object with mechanism and reason'


def check_decision(component: Component) -> str | None:
    if component.decision in DECISIONS:
        return None
    return f'decision must be one of {DECISIONS}'


COMPONENT_CHECKS: tuple[Callable[[Component], str | None], ...] = (
    check_kind,
    check_component_name,
    check_purpose,
    check_status,
    check_builder,
    check_advice,
    check_decision,
)


def component_errors(component: Component, seen: set[tuple[str, str]]) -> list[Finding]:
    label = f'component {component.name or "?"}'
    key = (component.kind, component.name)
    messages = [f'duplicate {key[0]}'] if key in seen else []
    seen.add(key)
    messages += [message for message in (check(component) for check in COMPONENT_CHECKS) if message]
    return [error(f'{label}: {message}') for message in messages]


def check_plan(plan: Plan) -> list[Finding]:
    findings = [error(message) for message in (check(plan) for check in PLAN_CHECKS) if message]
    if plan.author is None:
        findings.append(warning('author is missing; claude plugin validate warns without it'))
    seen: set[tuple[str, str]] = set()
    for component in plan.components:
        findings += component_errors(component, seen)
    return findings
