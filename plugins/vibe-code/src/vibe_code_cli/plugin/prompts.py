from msgspec import UnsetType

from ai_engineer_cli.plugin.kinds import KIND_SPECS
from ai_engineer_cli.plugin.layout import component_files, planned
from ai_engineer_cli.plugin.phases import Context
from ai_engineer_cli.plugin.record import Component, Plan, audience_of, distribution_of

PLUGIN_NAMESPACE = 'ai-engineer'
MARKETPLACE_ADD = 'claude plugin marketplace add <source>'
CLEAN_CACHE = 'with CLAUDE_CODE_PLUGIN_CACHE_DIR pointing at an empty directory'


def render_value(value: object) -> str:
    if isinstance(value, list):
        return ', '.join(str(item) for item in value)
    return str(value)


def answers_text(answers: dict[str, object]) -> str:
    parts = [f'{key.replace("_", " ")}: {render_value(value)}' for key, value in answers.items()]
    return '; '.join(parts)


def install_line(plan: Plan) -> str:
    distribution = distribution_of(plan)
    if not isinstance(distribution.install, UnsetType):
        return distribution.install
    if distribution.channel == 'local':
        return f'claude --plugin-dir ./{plan.name}'
    return f'claude plugin install {plan.name}@<marketplace> --scope project'


def install_steps(plan: Plan) -> list[str]:
    """The commands a user runs, in order: a marketplace has to be added before the install."""
    if distribution_of(plan).channel == 'marketplace':
        return [MARKETPLACE_ADD, install_line(plan)]
    return [install_line(plan)]


def planning_note(component: Component) -> str:
    advice = component.advice
    if advice is None:
        return ''
    return (
        f'Planning note: {advice.mechanism} was suggested for this ({advice.reason}); the '
        f'decision is to build it as a {component.kind}, so build it as one and do not re-open '
        'the question.'
    )


def prompt_opener(component: Component, root: str) -> str:
    spec = KIND_SPECS[component.kind]
    opener = spec.opener.format(name=component.name, root=root, purpose=component.purpose)
    return f'/{PLUGIN_NAMESPACE}:{spec.builder} {opener}' if spec.builder else opener


def ready_prompt(ctx: Context, component: Component) -> str:
    plan = ctx.plan
    audience = audience_of(plan)
    lines = [
        prompt_opener(component, ctx.root),
        '',
        (
            f'Plugin: {plan.name} ({", ".join(plan.kinds)}; audience: '
            f'{audience.who}, {audience.how}). Problem it solves: {plan.problem}'
        ),
        f'Files this component owns: {", ".join(component_files(component))}',
    ]
    if component.answers:
        answers = answers_text(component.answers)
        lines.append(f'Everything you would otherwise ask me: scope plugin; {answers}.')
    if component.advice:
        lines.append(planning_note(component))
    if component.facts:
        facts = ' '.join(f'{fact}.' for fact in component.facts)
        lines.append(f'Constraints from the plan: {facts}')
    lines.append(
        f'When done: flip component.{component.name}.status to built in PLAN.md and '
        'plugin-plan.json, then run /reload-plugins.'
    )
    return '\n'.join(lines)


def verify_prompt(ctx: Context) -> str:
    plan, root = ctx.plan, ctx.root
    checks = [
        f'- {KIND_SPECS[c.kind].label} `{c.name}`: {", ".join(component_files(c))}'
        for c in plan.components
    ]
    install = ' && '.join(f'`{step}`' for step in install_steps(plan))
    return '\n'.join(
        [
            f'Verify the plugin at {root} the way its users will get it.',
            '',
            (
                f'Run `claude plugin validate {root} --strict` and fix every error and warning. '
                f'Then load it with `claude --plugin-dir {root}` and, once more, through the '
                f'distribution channel with {install} (uninstall first if an older copy is '
                'installed). Run /reload-plugins after each edit. In each session confirm every '
                'component is discovered and works once:'
            ),
            *checks,
            '',
            (
                f'Skills: typing /{plan.name}: lists them and the description triggers on a '
                f'matching prompt. Agents: the typeahead after @agent-{plan.name}: shows '
                f'`{plan.name}:NAME` and a delegation returns. Hooks: /hooks lists them with '
                f'the plugin as source and one event fires. MCP: /mcp shows '
                f'`plugin:{plan.name}:NAME` and one tool call succeeds. Anything else the '
                '/plugin Errors tab reports is a failure. Report what was not discovered as an '
                'open question in PLAN.md rather than working around it silently.'
            ),
        ]
    )


def publish_detail(plan: Plan) -> str:
    license_check = (
        'Check LICENSE matches plugin.json, then '
        if plan.license
        else 'Confirm plugin.json omits license and no LICENSE file is shipped, then '
    )
    steps = ' && '.join(f'`{step}`' for step in install_steps(plan))
    if distribution_of(plan).channel == 'marketplace':
        return (
            f"{license_check}add or update the entry in the marketplace repository's "
            '`.claude-plugin/marketplace.json`: name, description, version and keywords from '
            'plugin.json, and a `source` object with `repo` and `ref` and the 40-char `sha` of '
            'the release commit pinned beside `ref` (a `ref` alone is a moving target with '
            f"hooks that run on every user's machine). Then `claude plugin marketplace update` "
            f'and {steps} {CLEAN_CACHE}.'
        )
    return (
        f'{license_check}install {CLEAN_CACHE} with {steps} and record the version that was '
        'verified.'
    )


def publish_prompt(ctx: Context) -> str:
    plan, root = ctx.plan, ctx.root
    outside = [
        f'- {item.need or item.what}: {item.mechanism} '
        f'({"to be decided" if isinstance(item.where, UnsetType) else item.where})'
        for item in plan.outside_plugin
    ]
    rollout = ['', 'Ship these alongside; a plugin cannot carry them:', *outside]
    lines = [
        (
            f'Publish the plugin at {root} (version {plan.version}, channel '
            f'{distribution_of(plan).channel}).'
        ),
        '',
        publish_detail(plan),
        *(rollout if outside else []),
    ]
    return '\n'.join(lines)


def final_sessions(ctx: Context) -> list[tuple[str, str, str]]:
    sessions = [('4.1', 'install and verify', verify_prompt(ctx))]
    if planned(ctx.plan):
        sessions.append(('4.2', 'publish', publish_prompt(ctx)))
    return sessions
