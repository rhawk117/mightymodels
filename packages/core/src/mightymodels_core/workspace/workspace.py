"""The repository the plugin works in: its root and its contained paths under `.mightymodels/`.

A persona report is the one path a symlink may not stand in for, wherever the symlink points.
Resolving the report would hide that its last part is one, so `Workspace.persona_report` looks at
the name as the reviewer wrote it before resolving it, and hands out a contained file only when
that name is no symlink.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .handoffs import HandoffFiles
from .paths import STATE_DIRECTORY, TICKET_DRAFT, TICKET_FILE, contained_in, review_parts

if TYPE_CHECKING:
    from mightymodels_core.primitives import RunId, Slug


@dataclass(slots=True, kw_only=True, frozen=True)
class PersonaReport:
    relative: str
    file: Path | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Workspace:
    root: Path
    state_directory: Path
    handoffs: HandoffFiles

    def contained(self, *parts: str) -> Path:
        return contained_in(self.state_directory, *parts)

    def relative_to_root(self, contained: Path) -> str:
        return str(Path(STATE_DIRECTORY).joinpath(contained.relative_to(self.state_directory)))

    def ticket_file(self, slug: Slug) -> Path:
        return self.contained(slug, TICKET_FILE)

    def ticket_draft(self, slug: Slug) -> Path:
        return self.contained(slug, TICKET_DRAFT)

    def task_brief(self, slug: Slug, number: int) -> Path:
        return self.contained(slug, 'briefs', f'task-{number:02d}.md')

    def review_directory(self, slug: Slug | None, run: RunId) -> Path:
        return self.contained(*review_parts(slug, run))

    def persona_report(self, slug: Slug | None, run: RunId, *, name: str) -> PersonaReport:
        parts = (*review_parts(slug, run), name)
        directory = self.review_directory(slug, run)
        is_symlink = self.state_directory.joinpath(*parts).is_symlink()
        return PersonaReport(
            relative=str(Path(self.relative_to_root(directory), name)),
            file=None if is_symlink else self.contained(*parts),
        )


def workspace_of(root: Path) -> Workspace:
    state_directory = root.joinpath(STATE_DIRECTORY).resolve()
    return Workspace(
        root=root,
        state_directory=state_directory,
        handoffs=HandoffFiles(state_directory=state_directory),
    )


def workspace_at(root: Path) -> Workspace:
    return workspace_of(root.resolve())
