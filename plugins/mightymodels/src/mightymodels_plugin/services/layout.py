"""Every path the plugin builds under `.mightymodels/`, each from a validated slug."""

from pathlib import Path

from mightymodels_plugin.db.repository import STATE_DIRECTORY
from mightymodels_plugin.models.slug import Slug


def ticket_directory(root: Path, slug: Slug) -> Path:
    return root.joinpath(STATE_DIRECTORY, slug.root)


def ticket_file(root: Path, slug: Slug) -> Path:
    return ticket_directory(root, slug).joinpath('ticket.yml')


def task_brief(root: Path, slug: Slug, number: int) -> Path:
    return ticket_directory(root, slug).joinpath('briefs', f'task-{number:02d}.md')


def investigation_ledger(root: Path, investigation: Slug) -> Path:
    runtime = root.joinpath(STATE_DIRECTORY, '.runtime', 'investigations')
    return runtime.joinpath(f'{investigation.root}.jsonl')
