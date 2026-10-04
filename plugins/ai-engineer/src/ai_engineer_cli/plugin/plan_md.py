from msgspec import UnsetType

from ai_engineer_cli.plugin.kinds import KIND_SPECS
from ai_engineer_cli.plugin.layout import component_files, layout_tree, tree_lines
from ai_engineer_cli.plugin.phases import PHASES, Context, Phase, phase_components, session_ids
from ai_engineer_cli.plugin.prompts import (
    final_sessions,
    install_steps,
    ready_prompt,
    render_value,
)
from ai_engineer_cli.plugin.record import Component, OutsideItem, Plan, audience_of, distribution_of

INTERVIEW = (
    ('A. Start', 'mode'),
    ('B. Problem and audience', 'problem'),
    ('C. Kind', 'kinds'),
    ('D. Identity', 'name'),
    ('E. Components', 'components'),
    ('F. Challenge', 'advice'),
    ('G. Layout', 'layout'),
    ('H. Distribution', 'distribution'),
)
RELOAD_NOTE = (
    'run /reload-plugins in a running session after edits, or develop with '
    'claude --plugin-dir ./<dir>'
)
RECORD_NOTE = (
    'plugin-plan.json is the machine record; flip component.NAME.status to built in both '
    'files when done'
)
STATUS_NOTE = (
    'Status moves from planned to built when the builder session has written the component; '
    'update this file and `plugin-plan.json` together.'
)
PHASES_NOTE = (
    'Phases run in order; sessions inside a phase are independent unless a prompt says '
    'otherwise. Paste each block into a Claude Code session opened at the plugin root; the '
    'builder skill takes the answers as given and asks only what the plan does not cover.'
)
LAYOUT_NOTE = (
    'Claude Code plugin layout: the manifest sits in `.claude-plugin/` and every other '
    'directory at the plugin root. `render` created the directories the planned components '
    'own and wrote the four plan files; every other path is owned by the session named '
    'beside it.'
)
LAYOUT_FACT = (
    'Claude Code plugin layout; the manifest is in .claude-plugin/, components sit at the '
    'plugin root'
)
OUTSIDE_NOTE = (
    'Needs the interview routed to a mechanism a plugin cannot ship; they are part of the '
    'rollout, not of this repository.'
)
AGENT_NOTE = (
    'Context for any session that builds or changes a component. One fact per line, stable '
    'keys: `grep "^component.NAME" PLAN.md` gives everything about one component, '
    '`grep "^phase\\."` the build order, `grep "^plugin\\."` the plugin-wide facts.'
)


def need_of(item: OutsideItem) -> str:
    return item.need or item.what


def where_of(item: OutsideItem) -> str:
    return 'to be decided' if isinstance(item.where, UnsetType) else item.where


def install_text(plan: Plan) -> str:
    return ' && '.join(install_steps(plan))


def advice_summary(plan: Plan) -> str:
    advised = [
        f'`{c.name}`: {c.advice.mechanism} suggested, decision {c.decision}'
        for c in plan.components
        if c.advice
    ]
    return '; '.join(advised) or 'nothing flagged'


def interview_values(plan: Plan) -> dict[str, str]:
    audience = audience_of(plan)
    distribution = distribution_of(plan)
    extension = any(c.status == 'built' for c in plan.components)
    ecosystem = f'; ecosystem {plan.ecosystem}' if plan.ecosystem else ''
    install = '' if isinstance(distribution.install, UnsetType) else f', `{distribution.install}`'
    return {
        'mode': 'extension of an existing plugin' if extension else 'new plugin',
        'problem': f'{plan.problem} Audience: {audience.who} ({audience.how}).',
        'kinds': ', '.join(plan.kinds) + ecosystem,
        'name': f'`{plan.name}`; keywords {", ".join(plan.keywords)}; "{plan.description}"',
        'components': ', '.join(f'{c.kind} `{c.name}`' for c in plan.components),
        'advice': advice_summary(plan),
        'layout': f'Claude Code plugin; {len(plan.components)} components; see Layout',
        'distribution': distribution.channel + install,
    }


def interview_summary(plan: Plan) -> list[str]:
    values = interview_values(plan)
    return [f'- {title}: {values[key]}' for title, key in INTERVIEW]


def layout_section(plan: Plan) -> list[str]:
    return [
        '### Layout',
        '',
        LAYOUT_NOTE,
        '',
        '```text',
        f'{plan.name}/',
        *tree_lines(layout_tree(plan)),
        '```',
        '',
    ]


def component_table(ctx: Context) -> list[str]:
    rows = [
        f'| {c.kind} | `{c.name}` | {c.status} | {ctx.sessions.get(c.name, "built")} | '
        f'`{c.builder or "manual"}` | {c.purpose} |'
        for c in ctx.plan.components
    ]
    return [
        '| kind | name | status | session | builder | purpose |',
        '|---|---|---|---|---|---|',
        *rows,
    ]


def session_block(title: str, prompt: str, *, note: str | None = None) -> list[str]:
    lines = [f'##### Session {title}', '']
    if note:
        lines += [note, '']
    return [*lines, '```text', prompt, '```', '']


def component_session(ctx: Context, component: Component) -> list[str]:
    title = f'{ctx.sessions[component.name]}: {component.kind} `{component.name}`'
    advice = component.advice
    note = (
        f'Planning note: {advice.mechanism} was suggested ({advice.reason}); decision: '
        f'{component.decision}.'
        if advice
        else None
    )
    return session_block(title, ready_prompt(ctx, component), note=note)


def phase_section(ctx: Context, phase: Phase) -> list[str]:
    lines: list[str] = [f'#### Phase {phase.number}: {phase.title}', '', phase.purpose, '']
    components = phase_components(ctx.plan, phase)
    if phase.kinds and not components:
        return [*lines, 'Nothing planned in this phase.', '']
    for component in components:
        lines += component_session(ctx, component)
    if not phase.kinds:
        for number, title, prompt in final_sessions(ctx):
            lines += session_block(f'{number}: {title}', prompt)
    return lines


def phases_section(ctx: Context) -> list[str]:
    lines: list[str] = ['### Phases', '', PHASES_NOTE, '']
    for phase in PHASES:
        lines += phase_section(ctx, phase)
    return lines


def closing_sections(plan: Plan) -> list[str]:
    built = [c for c in plan.components if c.status == 'built']
    lines: list[str] = []
    if built:
        rows = [f'- {c.kind} `{c.name}`: {c.purpose}' for c in built]
        lines += ['### Already built', '', *rows, '']
    if plan.outside_plugin:
        rows = [
            f'| {need_of(item)} | {item.mechanism} | {where_of(item)} |'
            for item in plan.outside_plugin
        ]
        header = ['| need | mechanism | where |', '|---|---|---|']
        lines += ['### Outside the plugin', '', OUTSIDE_NOTE, '', *header, *rows, '']
    if plan.open_questions:
        lines += ['### Open questions', '', *[f'- {q}' for q in plan.open_questions], '']
    return lines


def human_section(ctx: Context) -> list[str]:
    plan = ctx.plan
    return [
        '## Human',
        '',
        plan.description,
        '',
        '### Why',
        '',
        plan.problem,
        '',
        '### Interview decisions',
        '',
        *interview_summary(plan),
        '',
        *layout_section(plan),
        '### Components',
        '',
        *component_table(ctx),
        '',
        STATUS_NOTE,
        '',
        *phases_section(ctx),
        *closing_sections(plan),
    ]


def plugin_lines(plan: Plan, root: str) -> list[str]:
    audience = audience_of(plan)
    ecosystem = [f'plugin.ecosystem: {plan.ecosystem}'] if plan.ecosystem else []
    outside = [
        f'plugin.outside: {need_of(item)} -> {item.mechanism} ({where_of(item)})'
        for item in plan.outside_plugin
    ]
    return [
        f'plugin.name: {plan.name}',
        f'plugin.root: {root}',
        f'plugin.description: {plan.description}',
        f'plugin.problem: {plan.problem}',
        f'plugin.audience: {audience.who} ({audience.how})',
        f'plugin.kinds: {", ".join(plan.kinds)}',
        *ecosystem,
        f'plugin.layout: {LAYOUT_FACT}',
        f'plugin.distribution: {distribution_of(plan).channel}',
        f'plugin.install: {install_text(plan)}',
        f'plugin.reload: {RELOAD_NOTE}',
        f'plugin.record: {RECORD_NOTE}',
        *outside,
    ]


def phase_lines(plan: Plan) -> list[str]:
    lines: list[str] = []
    for phase in PHASES:
        names = ', '.join(c.name for c in phase_components(plan, phase))
        sessions = names or ('install and verify, publish' if not phase.kinds else 'none')
        lines.append(f'phase.{phase.number}: {phase.title}; sessions: {sessions}')
    return lines


def component_lines(ctx: Context, component: Component) -> list[str]:
    key = f'component.{component.name}'
    spec = KIND_SPECS[component.kind]
    answers = [
        f'{key}.answer.{name}: {render_value(value)}' for name, value in component.answers.items()
    ]
    facts = [f'{key}.fact: {fact}' for fact in component.facts]
    advice = component.advice
    advised = [f'{key}.advice: {advice.mechanism}: {advice.reason}'] if advice else []
    reference = [f'{key}.reference: {spec.reference}'] if spec.reference else []
    return [
        f'{key}.kind: {component.kind}',
        f'{key}.status: {component.status}',
        f'{key}.session: {ctx.sessions.get(component.name, "built")}',
        f'{key}.builder: {component.builder or "manual"}',
        *reference,
        f'{key}.purpose: {component.purpose}',
        *[f'{key}.file: {path}' for path in component_files(component)],
        *answers,
        *facts,
        *advised,
        f'{key}.decision: {component.decision}',
    ]


def agent_lines(ctx: Context) -> list[str]:
    plan = ctx.plan
    lines: list[str] = [*plugin_lines(plan, ctx.root), *phase_lines(plan)]
    for component in plan.components:
        lines += component_lines(ctx, component)
    return lines + [f'plugin.open: {question}' for question in plan.open_questions]


def render_plan_md(plan: Plan, root: str) -> str:
    ctx = Context(plan, root, session_ids(plan))
    lines = [
        f'# {plan.name}: plugin plan',
        '',
        *human_section(ctx),
        '## Agent',
        '',
        AGENT_NOTE,
        '',
        '```text',
        *agent_lines(ctx),
        '```',
        '',
    ]
    return '\n'.join(lines)


def render_readme(plan: Plan) -> str:
    ships = [f'- {KIND_SPECS[c.kind].label} `{c.name}`: {c.purpose}' for c in plan.components]
    lines = [
        f'# {plan.name}',
        '',
        plan.description,
        '',
        f'Built for {audience_of(plan).who}. {plan.problem}',
        '',
        '## Install',
        '',
        '```sh',
        *install_steps(plan),
        '```',
        '',
        '## What it ships',
        '',
        *ships,
        '',
        'See `PLAN.md` for the layout, the build phases and what is still planned.',
        '',
    ]
    return '\n'.join(lines)
