"""Containment: a path that resolves outside the state directory is refused."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import RunId
from mightymodels_core.workspace import (
    OutsideStateDirectoryError,
    Workspace,
    workspace_at,
)

from tests.core.workspace.workspace_builders import TICKET

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet

type PathRequest = Callable[[Workspace], object]

RUN = RunId('20260101-000000')
ESCAPES = 'resolves outside .mightymodels/'
REPORT_NAME = 'UNCLE-BOB-REPORT.md'


def ask_ticket_file(workspace: Workspace) -> object:
    return workspace.ticket_file(TICKET)


def ask_ticket_draft(workspace: Workspace) -> object:
    return workspace.ticket_draft(TICKET)


def ask_task_brief(workspace: Workspace) -> object:
    return workspace.task_brief(TICKET, 4)


def ask_ticket_review(workspace: Workspace) -> object:
    return workspace.review_directory(TICKET, RUN)


def ask_runtime_review(workspace: Workspace) -> object:
    return workspace.review_directory(None, RUN)


def ask_persona_report(workspace: Workspace) -> object:
    return workspace.persona_report(None, RUN, name=REPORT_NAME)


def ask_snapshot(workspace: Workspace) -> object:
    return workspace.handoffs.snapshot(TICKET)


def ask_archive(workspace: Workspace) -> object:
    return workspace.handoffs.archive(TICKET, 1)


def ask_live_debug(workspace: Workspace) -> object:
    return workspace.handoffs.live_debug(TICKET)


@dataclass(slots=True, kw_only=True, frozen=True)
class EscapingSymlink:
    name: str
    planted: tuple[str, ...]
    ask: PathRequest


ESCAPING_SYMLINKS = (
    EscapingSymlink(name='ticket-directory', planted=(TICKET,), ask=ask_ticket_file),
    EscapingSymlink(name='ticket-file', planted=(TICKET, 'ticket.yml'), ask=ask_ticket_file),
    EscapingSymlink(name='ticket-draft', planted=(TICKET, 'ticket.yml.tmp'), ask=ask_ticket_draft),
    EscapingSymlink(name='briefs', planted=(TICKET, 'briefs'), ask=ask_task_brief),
    EscapingSymlink(name='ticket-reviews', planted=(TICKET, 'review'), ask=ask_ticket_review),
    EscapingSymlink(name='runtime', planted=('.runtime',), ask=ask_runtime_review),
    EscapingSymlink(
        name='run-directory',
        planted=('.runtime', 'reviews', RUN),
        ask=ask_persona_report,
    ),
    EscapingSymlink(name='handoffs', planted=(TICKET, 'handoffs'), ask=ask_snapshot),
    EscapingSymlink(name='archives', planted=('archives',), ask=ask_archive),
    EscapingSymlink(name='debug-note', planted=(TICKET, 'whats-broken.md'), ask=ask_live_debug),
)


def escaping_symlink_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'escaping', [pytest.param(escaping, id=escaping.name) for escaping in ESCAPING_SYMLINKS]
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ClimbingParts:
    name: str
    parts: tuple[str, ...]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def workspace_climbing_parts_cases() -> pytest.MarkDecorator:
    scenarios = [
        ClimbingParts(name='parent', parts=('..', 'outside')),
        ClimbingParts(name='nested-parent', parts=(TICKET, '..', '..', 'outside')),
        ClimbingParts(name='absolute', parts=('/etc',)),
    ]
    return pytest.mark.parametrize('climbing', [scenario.param for scenario in scenarios])


class TestSymlinkBelowTheStateDirectory:
    @pytest.fixture
    def workspace_with_a_dangling_symlink(self, state: Path, tmp_path: Path) -> Workspace:
        state.joinpath(TICKET).symlink_to(tmp_path.joinpath('never-created'))
        return workspace_at(state.parent)

    @pytest.fixture
    def workspace_with_a_symlink_that_stays_inside(self, state: Path) -> Workspace:
        state.joinpath('first-name').mkdir()
        state.joinpath(TICKET).symlink_to(state.joinpath('first-name'))
        return workspace_at(state.parent)

    @pytest.fixture
    def workspace_with_a_symlink_to_outside(
        self, tmp_path: Path, escaping: EscapingSymlink
    ) -> Workspace:
        state = tmp_path.joinpath('checkout', '.mightymodels')
        outside = tmp_path.joinpath('outside')
        state.mkdir(parents=True)
        outside.mkdir()
        planted = state.joinpath(*escaping.planted)
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.symlink_to(outside)
        return workspace_at(state.parent)

    @escaping_symlink_cases()
    def test_a_symlink_that_leads_outside_is_refused_wherever_it_sits(
        self, workspace_with_a_symlink_to_outside: Workspace, escaping: EscapingSymlink
    ) -> None:
        with pytest.raises(OutsideStateDirectoryError) as refusal:
            escaping.ask(workspace_with_a_symlink_to_outside)

        assert refusal.value.shown.startswith('.mightymodels/')
        assert ESCAPES in str(refusal.value)

    def test_a_dangling_symlink_is_refused_before_anything_is_created_through_it(
        self, workspace_with_a_dangling_symlink: Workspace, tmp_path: Path
    ) -> None:
        with pytest.raises(OutsideStateDirectoryError):
            workspace_with_a_dangling_symlink.ticket_file(TICKET)

        assert not tmp_path.joinpath('never-created').exists()

    def test_a_symlink_that_stays_inside_the_state_directory_is_followed(
        self, workspace_with_a_symlink_that_stays_inside: Workspace, state: Path
    ) -> None:
        ticket = workspace_with_a_symlink_that_stays_inside.ticket_file(TICKET)

        assert ticket == state.joinpath('first-name', 'ticket.yml')


class TestStateDirectoryBoundary:
    @pytest.fixture
    def workspace(self, checkout: Path) -> Workspace:
        return workspace_at(checkout)

    @pytest.fixture
    def workspace_whose_state_directory_is_a_symlink(
        self, checkout: Path, outside: Path
    ) -> Workspace:
        checkout.joinpath('.mightymodels').symlink_to(outside)
        return workspace_at(checkout)

    def test_a_symlinked_state_directory_holds_the_paths_and_keeps_their_shown_names(
        self, workspace_whose_state_directory_is_a_symlink: Workspace, outside: Path
    ) -> None:
        linked = workspace_whose_state_directory_is_a_symlink
        ticket = linked.ticket_file(TICKET)

        assert ticket == outside.joinpath(TICKET, 'ticket.yml')
        assert linked.relative_to_root(ticket) == f'.mightymodels/{TICKET}/ticket.yml'

    @workspace_climbing_parts_cases()
    def test_parts_that_climb_out_of_the_state_directory_are_refused(
        self, workspace: Workspace, climbing: ClimbingParts
    ) -> None:
        with pytest.raises(OutsideStateDirectoryError):
            workspace.contained(*climbing.parts)


class TestPersonaReport:
    @pytest.fixture
    def workspace(self, checkout: Path) -> Workspace:
        return workspace_at(checkout)

    @pytest.fixture
    def workspace_with_a_symlinked_report(self, state: Path, outside: Path) -> Workspace:
        run_directory = state.joinpath('.runtime', 'reviews', RUN)
        run_directory.mkdir(parents=True)
        run_directory.joinpath(REPORT_NAME).symlink_to(outside)
        return workspace_at(state.parent)

    def test_a_report_that_is_no_symlink_is_a_contained_file(self, workspace: Workspace) -> None:
        report = workspace.persona_report(None, RUN, name=REPORT_NAME)

        assert report.file == workspace.state_directory.joinpath(
            '.runtime', 'reviews', RUN, REPORT_NAME
        )
        assert report.relative == f'.mightymodels/.runtime/reviews/{RUN}/{REPORT_NAME}'

    def test_a_report_that_is_a_symlink_has_no_file(
        self, workspace_with_a_symlinked_report: Workspace
    ) -> None:
        report = workspace_with_a_symlinked_report.persona_report(None, RUN, name=REPORT_NAME)

        assert report.file is None
