"""The slug is the only caller-chosen text that becomes a path, so it is checked in one type."""

import asyncio
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.types import CallToolResult
from mightymodels_plugin.cli import main
from mightymodels_plugin.db.checkout import open_checkout
from mightymodels_plugin.db.tables import ReviewFindingRow
from mightymodels_plugin.models.review import StartPayload
from mightymodels_plugin.models.slug import (
    SLUG_LIMIT,
    SLUG_PATTERN,
    InvalidSlugError,
    Slug,
    parsed_slug,
)
from mightymodels_plugin.models.ticket import TicketAnswers
from mightymodels_plugin.server import TOOLS, build_server
from mightymodels_plugin.services import ticket
from mightymodels_plugin.services.layout import investigation_ledger, task_brief, ticket_file
from pydantic import ValidationError
from pytest_mock import MockerFixture
from sqlalchemy import select

type GitRunner = Callable[..., str]

REJECTED = 2
OUTSIDE = '../../../outside'
ANSWERS = {
    'summary': 'Retry queue drains slowly',
    'scope': 'med',
    'compaction': False,
    'branch': 'fix/retry-queue',
    'context': ['drain loop sleeps between batches'],
}
HOSTILE = [
    pytest.param('../outside', id='parent'),
    pytest.param('..', id='dot-dot'),
    pytest.param('a/../../b', id='nested-parent'),
    pytest.param('a/b', id='separator'),
    pytest.param('a\\b', id='backslash'),
    pytest.param('/etc', id='absolute'),
    pytest.param('.', id='dot'),
    pytest.param('.runtime', id='hidden'),
    pytest.param('a..b', id='inner-dots'),
    pytest.param('', id='empty'),
    pytest.param('a\n', id='trailing-newline'),
    pytest.param('a\x00b', id='nul'),
    pytest.param('-rf', id='option'),
    pytest.param('~root', id='tilde'),
    pytest.param('retry queue', id='space'),
    pytest.param('x' * (SLUG_LIMIT + 1), id='too-long'),
]
HOSTILE_RUN_IDS = [
    pytest.param('../../etc', id='parents'),
    pytest.param('..', id='dot-dot'),
    pytest.param('20260101-000000/../x', id='trailing-parent'),
    pytest.param('20260101-000000\n', id='trailing-newline'),
    pytest.param('/etc', id='absolute'),
    pytest.param('', id='empty'),
]
RUN_CALLS = [
    pytest.param({'action': 'add', 'payload': {'persona': 'merge-vader'}}, id='add'),
    pytest.param({'action': 'gate'}, id='gate'),
    pytest.param(
        {'action': 'dispose', 'payload': {'by': 'user', 'decisions': {'F1': {'decision': 'fix'}}}},
        id='dispose',
    ),
    pytest.param(
        {'action': 'resolve', 'payload': {'finding': 'F1', 'result': 'failed', 'reason': 'r'}},
        id='resolve',
    ),
    pytest.param({'action': 'report'}, id='report'),
]
START_PAYLOAD = {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'}
TOOL_CALLS = (
    ('ticket-write', 'ticket', {'action': 'write', 'fields': ANSWERS}),
    ('ticket-validate', 'ticket', {'action': 'validate'}),
    ('ticket-show', 'ticket', {'action': 'show'}),
    ('ticket-context', 'ticket', {'action': 'update-context', 'fields': {'context': ['x']}}),
    (
        'task-start',
        'task',
        {'action': 'start', 'task_id': 'T1', 'change': {'by': 'engineer', 'owned': ['a.py']}},
    ),
    ('task-verify', 'task', {'action': 'verify', 'task_id': 'T1', 'change': {'commit': 'HEAD'}}),
    ('task-show', 'task', {'action': 'show'}),
    ('task-ready', 'task', {'action': 'ready'}),
    (
        'contract-approve',
        'contract',
        {'action': 'approve', 'commands': [{'id': 'I1', 'argv': ['true'], 'approved_by': 'user'}]},
    ),
    ('contract-status', 'contract', {'action': 'status'}),
)
CALLS = [pytest.param(name, arguments, id=label) for label, name, arguments in TOOL_CALLS]


LEAKING_REPORT = """## Findings

### High

#### UB-1 | [G5] Hardcoded password=hunter22 in the store \u2014 `src/store.py:4`

- Evidence (convention): ruff.toml S105; src/a.py:1, src/b.py:2
- Fix: Read the secret from the environment instead of ghp_abcdefghijklmnopqrstuvwxyzABCDEF123456.
- Verify: `rg -n 'password' src/store.py`
"""


def tree(top: Path) -> dict[str, bytes]:
    files = (path for path in sorted(top.rglob('*')) if path.is_file())
    return {str(path.relative_to(top)): path.read_bytes() for path in files}


async def call_tool(name: str, arguments: dict[str, object]) -> CallToolResult:
    async with Client(build_server()) as client:
        return await client.call_tool(name, arguments)


async def tool_schemas() -> dict[str, dict[str, Any]]:
    async with Client(build_server()) as client:
        listed = await client.list_tools()
    return {tool.name: tool.input_schema for tool in listed.tools}


@pytest.fixture
def project(repository: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(repository))
    repository.joinpath('outside.jsonl').write_text('', encoding='utf-8')
    return repository


class TestSlugType:
    @pytest.mark.parametrize('raw', HOSTILE)
    def test_slug_confinement_refuses_a_separator_or_a_parent_reference(self, raw: str) -> None:
        assert isinstance(parsed_slug(raw), InvalidSlugError)
        with pytest.raises(ValidationError):
            Slug(raw)

    @pytest.mark.parametrize('raw', ['retry-queue', 'T3', '20260928-missing', 'a_b', 'x' * 64])
    def test_slug_confinement_keeps_every_path_under_the_state_directory(
        self, raw: str, tmp_path: Path
    ) -> None:
        slug = Slug(raw)
        state = tmp_path.joinpath('.mightymodels')

        assert ticket_file(tmp_path, slug) == state.joinpath(raw, 'ticket.yml')
        assert task_brief(tmp_path, slug, 3) == state.joinpath(raw, 'briefs', 'task-03.md')
        assert investigation_ledger(tmp_path, slug) == state.joinpath(
            '.runtime', 'investigations', f'{raw}.jsonl'
        )

    def test_slug_confinement_every_slug_taking_tool_uses_the_one_slug_type(self) -> None:
        taking_a_slug = [tool for tool in TOOLS if 'slug' in inspect.signature(tool).parameters]
        annotations = [
            inspect.signature(tool).parameters['slug'].annotation for tool in taking_a_slug
        ]

        assert [tool.__name__ for tool in taking_a_slug] == ['ticket', 'task', 'contract']
        assert annotations == [Slug, Slug, Slug]

    def test_slug_confinement_the_one_slug_type_is_the_review_start_payloads_slug(self) -> None:
        assert StartPayload.model_fields['slug'].annotation == Slug | None

    def test_slug_confinement_every_tool_schema_carries_the_slug_pattern(self) -> None:
        schemas = {
            name: schema
            for name, schema in asyncio.run(tool_schemas()).items()
            if 'slug' in schema['properties']
        }

        assert sorted(schemas) == ['contract', 'task', 'ticket']
        assert all(
            (
                schema['properties']['slug'],
                schema['$defs']['Slug']['$ref'],
                schema['$defs']['SlugText'],
            )
            == (
                {'$ref': '#/$defs/Slug'},
                '#/$defs/SlugText',
                {'maxLength': SLUG_LIMIT, 'pattern': SLUG_PATTERN, 'type': 'string'},
            )
            for schema in schemas.values()
        )


@pytest.mark.usefixtures('project')
class TestHostileSlug:
    @pytest.mark.parametrize('raw', HOSTILE)
    @pytest.mark.parametrize(('name', 'arguments'), CALLS)
    def test_slug_confinement_a_tool_reads_and_writes_nothing_for_a_hostile_slug(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        *,
        name: str,
        arguments: dict[str, object],
        raw: str,
    ) -> None:
        opened = mocker.patch('mightymodels_plugin.db.checkout.open_repository')
        before = tree(tmp_path)

        result = asyncio.run(call_tool(name, {**arguments, 'slug': raw}))

        assert result.is_error
        opened.assert_not_called()
        assert tree(tmp_path) == before

    @pytest.mark.parametrize('raw', HOSTILE)
    def test_slug_confinement_verify_run_reads_and_writes_nothing_for_a_hostile_slug(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        *,
        raw: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        opened = mocker.patch('mightymodels_plugin.db.checkout.open_repository')
        before = tree(tmp_path)

        code = main(['verify', 'run', f'--slug={raw}', '--all'])

        assert code == REJECTED
        assert 'is not a slug' in capsys.readouterr().err
        opened.assert_not_called()
        assert tree(tmp_path) == before


class TestInsideTheStateDirectory:
    def stage(self, root: Path, investigations: list[str]) -> str:
        answers = TicketAnswers.model_validate({**ANSWERS, 'investigations': investigations})
        try:
            with open_checkout(root) as checkout:
                ticket.write(checkout, Slug('retry-queue'), answers)
                return ticket.validate(checkout, Slug('retry-queue')).text
        except ticket.InvalidTicketError as error:
            return str(error)

    def test_slug_confinement_a_written_investigation_id_cannot_name_a_file_outside(
        self, project: Path
    ) -> None:
        assert f'investigation {OUTSIDE} is not a valid id' in self.stage(project, [OUTSIDE])
        assert not ticket_file(project, Slug('retry-queue')).exists()

    def test_slug_confinement_a_hand_edited_investigation_id_cannot_name_a_file_outside(
        self, project: Path
    ) -> None:
        self.stage(project, [])
        path = ticket_file(project, Slug('retry-queue'))
        text = path.read_text(encoding='utf-8')
        path.write_text(f'{text}  - "{OUTSIDE}"\n', encoding='utf-8')

        with pytest.raises(ticket.InvalidTicketError) as error, open_checkout(project) as checkout:
            ticket.validate(checkout, Slug('retry-queue'))

        assert error.value.problems == [f'investigation {OUTSIDE} is not a valid id']

    def test_slug_confinement_a_valid_slug_writes_only_under_the_state_directory(
        self, project: Path, git: GitRunner
    ) -> None:
        results = [
            asyncio.run(call_tool(name, {**arguments, 'slug': 'retry-queue'}))
            for _, name, arguments in TOOL_CALLS
        ]

        written = {Path(name).parts[0] for name in tree(project)} - {'.git', 'outside.jsonl'}
        assert not any(result.is_error for result in results)
        assert written == {'.mightymodels'}
        assert git(project, 'status', '--porcelain') == '?? outside.jsonl\n'


@pytest.mark.usefixtures('project')
class TestReviewConfinement:
    @pytest.mark.parametrize('raw', HOSTILE)
    def test_slug_confinement_review_start_reads_and_writes_nothing_for_a_hostile_slug(
        self, tmp_path: Path, mocker: MockerFixture, raw: str
    ) -> None:
        opened = mocker.patch('mightymodels_plugin.db.checkout.open_repository')
        before = tree(tmp_path)

        payload = {**START_PAYLOAD, 'scope': 'ticket', 'base': 'main', 'slug': raw}
        result = asyncio.run(call_tool('review', {'action': 'start', 'payload': payload}))

        assert result.is_error
        opened.assert_not_called()
        assert tree(tmp_path) == before

    @pytest.mark.parametrize('raw', HOSTILE_RUN_IDS)
    @pytest.mark.parametrize('arguments', RUN_CALLS)
    def test_slug_confinement_a_path_shaped_run_id_reads_and_writes_nothing(
        self, tmp_path: Path, mocker: MockerFixture, arguments: dict[str, object], raw: str
    ) -> None:
        opened = mocker.patch('mightymodels_plugin.db.checkout.open_repository')
        before = tree(tmp_path)

        result = asyncio.run(call_tool('review', {**arguments, 'run_id': raw}))

        assert result.is_error
        opened.assert_not_called()
        assert tree(tmp_path) == before

    def test_slug_confinement_a_run_without_a_ticket_keeps_its_directory_under_runtime(
        self, project: Path
    ) -> None:
        result = asyncio.run(call_tool('review', {'action': 'start', 'payload': START_PAYLOAD}))

        run = result.structured_content['run_id']
        state = project.joinpath('.mightymodels')
        assert not result.is_error
        assert state.joinpath('.runtime', 'reviews', run).is_dir()
        assert {path.name for path in state.iterdir()} == {'.runtime', 'mightymodels.db'}

    def test_slug_confinement_a_run_with_a_ticket_keeps_its_directory_under_the_ticket(
        self, project: Path
    ) -> None:
        payload = {**START_PAYLOAD, 'scope': 'ticket', 'base': 'main', 'slug': 'retry-queue'}
        result = asyncio.run(call_tool('review', {'action': 'start', 'payload': payload}))

        run = result.structured_content['run_id']
        state = project.joinpath('.mightymodels')
        assert not result.is_error
        assert state.joinpath('retry-queue', 'review', run).is_dir()
        assert {path.name for path in state.iterdir()} == {'retry-queue', 'mightymodels.db'}

    def test_slug_confinement_a_report_with_secrets_is_redacted_in_the_stored_rows(
        self, project: Path
    ) -> None:
        started = asyncio.run(call_tool('review', {'action': 'start', 'payload': START_PAYLOAD}))
        run = started.structured_content['run_id']
        report = project.joinpath('.mightymodels', '.runtime', 'reviews', run)
        report.joinpath('UNCLE-BOB-REPORT.md').write_text(LEAKING_REPORT, encoding='utf-8')

        added = asyncio.run(
            call_tool(
                'review', {'action': 'add', 'run_id': run, 'payload': {'persona': 'uncle-bob'}}
            )
        )

        with open_checkout(project) as checkout:
            rows = checkout.session.scalars(select(ReviewFindingRow)).all()
            stored = ' '.join(
                str(getattr(row, column.name)) for row in rows for column in row.__table__.columns
            )
        assert not added.is_error
        assert 'hunter22' not in stored
        assert 'ghp_' not in stored
        assert 'Hardcoded [REDACTED:assignment] in the store' in stored
