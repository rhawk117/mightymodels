"""The `ticket` tool's service: ticket.yml stays a file, and validating it stages a row.

`write` renders the interview answers into ticket.yml and refuses to overwrite a ticket the
user may have tweaked. `validate` reads the file back, hand edits included, and stages or
refreshes the ticket's row without touching task progress. `update_context` replaces the
context lines in the file and restages it.
"""

from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from mightymodels_plugin.db.checkout import Checkout
from mightymodels_plugin.db.tables import TicketRow
from mightymodels_plugin.errors import StateError
from mightymodels_plugin.models.slug import InvalidSlugError, Slug, parsed_slug
from mightymodels_plugin.models.ticket import (
    TicketAnswers,
    TicketContext,
    TicketSection,
    TicketStatus,
    TicketView,
    Tracker,
    WorkUnit,
)
from mightymodels_plugin.routing import Scope, Worker
from mightymodels_plugin.services.clock import now
from mightymodels_plugin.services.layout import investigation_ledger, ticket_file
from mightymodels_plugin.services.ticket_file import (
    CONTEXT_KEY,
    PRIMARY_AGENT,
    Node,
    parse,
    ticket_text,
    with_context,
)

CONTEXT_LIMIT = 6
TOP_LEVEL = frozenset(
    {
        'task',
        'summary',
        'triaged-at',
        CONTEXT_KEY,
        'companion-docs',
        'subagent-models',
        'handoff-context',
        'investigations',
    }
)
COMPANION_KEYS = frozenset({'issue-number', 'jira-key', 'reference-urls'})
HANDOFF_KEYS = frozenset({'scope', 'plan-first', 'branch-name', 'worktrees-okay'})
KNOWN_WORKERS = frozenset({PRIMARY_AGENT, *(worker.value for worker in Worker)})
IMPLEMENTERS = frozenset({Worker.ENGINEER.value, Worker.ARCHITECT.value})

type Check = tuple[bool, str]


class TicketExistsError(StateError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} exists; edit it by hand, then run validate')
        self.path = path


class MissingTicketError(StateError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} does not exist; run write first')
        self.path = path


class InvalidTicketError(StateError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__('ticket.yml is invalid:\n  ' + '\n  '.join(problems))
        self.problems = problems


class NotStagedError(StateError):
    def __init__(self, slug: Slug) -> None:
        super().__init__(f'{slug} is not staged; stage the ticket with open-ticket first')
        self.slug = slug


def as_mapping(node: Node) -> dict[str, Node]:
    return node if isinstance(node, dict) else {}


def as_list(node: Node) -> list[Node]:
    return node if isinstance(node, list) else []


def failed(checks: Iterable[Check]) -> list[str]:
    return [message for passed, message in checks if not passed]


def top_problems(tree: dict[str, Node], slug: Slug) -> list[str]:
    unknown = sorted(set(tree) - TOP_LEVEL)
    context = tree.get(CONTEXT_KEY)
    return failed(
        (
            (not unknown, f'unknown top-level keys {unknown}; no consumer reads them'),
            (tree.get('task') == slug.root, f'task must be {slug.root!r}'),
            (bool(tree.get('summary')), 'summary is empty'),
            (
                isinstance(context, list) and 1 <= len(context) <= CONTEXT_LIMIT,
                f'context must be a list of 1 to {CONTEXT_LIMIT} lines',
            ),
        )
    )


def model_problems(models: dict[str, Node]) -> list[str]:
    unknown = sorted(set(models) - KNOWN_WORKERS)
    missing = sorted(IMPLEMENTERS - {worker for worker, model in models.items() if model})
    return failed(
        (
            (not unknown, f'subagent-models has unknown workers {unknown}'),
            (not missing, f'subagent-models needs a model for {missing}'),
        )
    )


def handoff_problems(handoff: dict[str, Node]) -> list[str]:
    unknown = sorted(set(handoff) - HANDOFF_KEYS)
    scopes = sorted(scope.value for scope in Scope)
    return failed(
        (
            (not unknown, f'handoff-context has unknown keys {unknown}'),
            (handoff.get('scope') in scopes, f'scope must be one of {scopes}'),
            (isinstance(handoff.get('plan-first'), bool), 'plan-first must be a bool'),
            (bool(handoff.get('branch-name')), 'branch-name is empty'),
        )
    )


def companion_problems(companions: dict[str, Node]) -> list[str]:
    unknown = sorted(set(companions) - COMPANION_KEYS)
    issue = companions.get('issue-number')
    return failed(
        (
            (not unknown, f'companion-docs has unknown keys {unknown}'),
            (issue is None or isinstance(issue, int), 'issue-number must be a number'),
        )
    )


def investigation_problem(root: Path, investigation: Node) -> str | None:
    slug = parsed_slug(str(investigation))
    if isinstance(slug, InvalidSlugError):
        return f'investigation {investigation} is not a valid id'
    if not investigation_ledger(root, slug).is_file():
        return f'investigation {investigation} has no ledger file'
    return None


def investigation_problems(tree: dict[str, Node], root: Path) -> list[str]:
    investigations = tree.get('investigations') or []
    if not isinstance(investigations, list):
        return ['investigations must be a list']
    problems = (investigation_problem(root, investigation) for investigation in investigations)
    return [problem for problem in problems if problem is not None]


def checked_tree(source: str, root: Path, slug: Slug) -> dict[str, Node]:
    tree = parse(source)
    problems = [
        *top_problems(tree, slug),
        *model_problems(as_mapping(tree.get('subagent-models'))),
        *handoff_problems(as_mapping(tree.get('handoff-context'))),
        *companion_problems(as_mapping(tree.get('companion-docs'))),
        *investigation_problems(tree, root),
    ]
    if problems:
        raise InvalidTicketError(problems)
    return tree


def section_of(tree: dict[str, Node], checkout: Checkout, slug: Slug) -> TicketSection:
    handoff = as_mapping(tree.get('handoff-context'))
    companions = as_mapping(tree.get('companion-docs'))
    fields = {
        'ticket': str(ticket_file(checkout.root, slug).relative_to(checkout.root)),
        'summary': tree.get('summary'),
        'branch': handoff.get('branch-name'),
        'scope': handoff.get('scope'),
        'plan_first': handoff.get('plan-first'),
        'models': as_mapping(tree.get('subagent-models')),
        'tracker': {'issue': companions.get('issue-number'), 'jira': companions.get('jira-key')},
        'context': as_list(tree.get(CONTEXT_KEY)),
        'validated_at': now(),
    }
    try:
        return TicketSection.model_validate(fields)
    except ValidationError as error:
        problems = [
            f'{".".join(map(str, detail["loc"]))}: {detail["msg"]}' for detail in error.errors()
        ]
        raise InvalidTicketError(problems) from error


def unit_of(row: TicketRow) -> WorkUnit:
    section = TicketSection(
        ticket=row.ticket,
        summary=row.summary,
        branch=row.branch,
        scope=Scope(row.scope),
        plan_first=row.plan_first,
        models=row.models,
        tracker=Tracker(issue=row.issue, jira=row.jira),
        context=tuple(row.context),
        validated_at=row.validated_at,
    )
    return WorkUnit(
        slug=Slug(row.slug),
        status=TicketStatus(row.status),
        ticket=section,
        investigations=tuple(row.investigations),
    )


def staged_row(checkout: Checkout, slug: Slug) -> TicketRow:
    row = checkout.session.get(TicketRow, slug.root)
    if row is None:
        raise NotStagedError(slug)
    return row


def stage(checkout: Checkout, slug: Slug, tree: dict[str, Node]) -> WorkUnit:
    section = section_of(tree, checkout, slug)
    existing = checkout.session.get(TicketRow, slug.root)
    previous = [] if existing is None else existing.investigations
    declared = [str(investigation) for investigation in as_list(tree.get('investigations'))]
    added = [investigation for investigation in declared if investigation not in previous]
    row = TicketRow(
        slug=slug.root,
        status=TicketStatus.STAGED if existing is None else existing.status,
        ticket=section.ticket,
        summary=section.summary,
        branch=section.branch,
        scope=section.scope,
        plan_first=section.plan_first,
        issue=section.tracker.issue,
        jira=section.tracker.jira,
        models=section.models,
        context=list(section.context),
        investigations=[*previous, *added],
        validated_at=section.validated_at,
    )
    return unit_of(checkout.session.merge(row))


def atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def staged_text(unit: WorkUnit) -> str:
    return f'staged {unit.slug} (status {unit.status}, {len(unit.investigations)} investigations)\n'


def write(checkout: Checkout, slug: Slug, answers: TicketAnswers) -> TicketView:
    path = ticket_file(checkout.root, slug)
    if path.exists():
        raise TicketExistsError(path)
    text = ticket_text(slug, answers)
    checked_tree(text, checkout.root, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, text)
    relative = path.relative_to(checkout.root)
    return TicketView(text=f'wrote {relative}; review it, then run validate\n')


def validate(checkout: Checkout, slug: Slug) -> TicketView:
    path = ticket_file(checkout.root, slug)
    if not path.is_file():
        raise MissingTicketError(path)
    tree = checked_tree(path.read_text(encoding='utf-8'), checkout.root, slug)
    unit = stage(checkout, slug, tree)
    return TicketView(text=f'valid; {staged_text(unit)}', unit=unit)


def show(checkout: Checkout, slug: Slug) -> TicketView:
    unit = unit_of(staged_row(checkout, slug))
    return TicketView(text=staged_text(unit), unit=unit)


def update_context(checkout: Checkout, slug: Slug, change: TicketContext) -> TicketView:
    path = ticket_file(checkout.root, slug)
    if not path.is_file():
        raise MissingTicketError(path)
    text = with_context(path.read_text(encoding='utf-8'), change.context)
    unit = stage(checkout, slug, checked_tree(text, checkout.root, slug))
    atomic_write(path, text)
    return TicketView(text=f'context updated; {staged_text(unit)}', unit=unit)
