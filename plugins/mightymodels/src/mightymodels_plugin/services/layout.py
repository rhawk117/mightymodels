"""Every path the plugin builds under `.mightymodels/`, each from a validated slug."""

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from mightymodels_plugin.db.repository import STATE_DIRECTORY
from mightymodels_plugin.models.review import Persona
from mightymodels_plugin.models.run_id import RunId
from mightymodels_plugin.models.slug import Slug

REPORT_FILES: Mapping[Persona, str] = MappingProxyType(
    {
        Persona.MERGE_VADER: 'MERGE-VADER-REPORT.md',
        Persona.UNCLE_BOB: 'UNCLE-BOB-REPORT.md',
    }
)


def ticket_directory(root: Path, slug: Slug) -> Path:
    return root.joinpath(STATE_DIRECTORY, slug.root)


def ticket_file(root: Path, slug: Slug) -> Path:
    return ticket_directory(root, slug).joinpath('ticket.yml')


def task_brief(root: Path, slug: Slug, number: int) -> Path:
    return ticket_directory(root, slug).joinpath('briefs', f'task-{number:02d}.md')


def investigation_ledger(root: Path, investigation: Slug) -> Path:
    runtime = root.joinpath(STATE_DIRECTORY, '.runtime', 'investigations')
    return runtime.joinpath(f'{investigation.root}.jsonl')


def review_directory(root: Path, slug: Slug | None, run: RunId) -> Path:
    if slug is None:
        return root.joinpath(STATE_DIRECTORY, '.runtime', 'reviews', run.root)
    return ticket_directory(root, slug).joinpath('review', run.root)


def persona_report(root: Path, slug: Slug | None, run: RunId, *, persona: Persona) -> Path:
    return review_directory(root, slug, run).joinpath(REPORT_FILES[persona])
