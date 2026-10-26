from typing import TYPE_CHECKING, Literal

import anyio
import pytest
from mcp.types import ToolAnnotations
from mightymodels_mcp.forms.needs_input import NEEDS_INPUT
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.icons import load_icon

from mcp import Client
from tests.mcp.review.review_harness import (
    ALL_ANSWERED,
    REPORT_NAMES,
    create_review_harness,
    merge_vader_report,
    uncle_bob_report,
)
from tests.mcp.server.server_harness import view_of
from tests.mcp.ticket.ticket_harness import SLUG, RecordingAnswerer

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.mcp.review.review_harness import ReviewHarness, StartedRun
    from tests.mcp.server.server_harness import ServerHarness

type FormAction = Literal['accept', 'decline', 'cancel']

WRITES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
UNKNOWN_RUN = '20200101-000000'
EMPHASIS_FORM = (
    f'{NEEDS_INPUT}\nWhat should the review emphasize?\n'
    'choices: release-readiness, maintainability, balanced, custom\npass: emphasis\n'
)


def listed_tool_cases() -> pytest.MarkDecorator:
    tools: list[ParameterSet] = [
        pytest.param('review_start', 'Start a review', WRITES, id='start'),
        pytest.param('review_override', "Override a review's models", WRITES, id='override'),
        pytest.param('review_add', "Add a reviewer's report", WRITES, id='add'),
        pytest.param('review_gate', 'Gate a review', READS, id='gate'),
        pytest.param('review_report', 'Report a review', READS, id='report'),
        pytest.param('review_list', 'List the reviews', READS, id='list'),
    ]
    return pytest.mark.parametrize(('name', 'title', 'annotations'), tools)


def unanswered_action_cases() -> pytest.MarkDecorator:
    actions: list[ParameterSet] = [
        pytest.param('decline', id='decline'),
        pytest.param('cancel', id='cancel'),
    ]
    return pytest.mark.parametrize('action', actions)


def unknown_run_cases() -> pytest.MarkDecorator:
    calls: list[ParameterSet] = [
        pytest.param('review_override', {}, id='override'),
        pytest.param('review_add', {'persona': 'uncle-bob'}, id='add'),
        pytest.param('review_gate', {}, id='gate'),
        pytest.param('review_report', {}, id='report'),
    ]
    return pytest.mark.parametrize(('name', 'extra'), calls)


@pytest.fixture
async def harness(server_harness: ServerHarness) -> ReviewHarness:
    return await create_review_harness(server_harness)


@pytest.fixture
async def started(harness: ReviewHarness) -> StartedRun:
    return await harness.start()


@pytest.fixture
async def reported(harness: ReviewHarness, started: StartedRun) -> StartedRun:
    await harness.write_report(started, 'merge-vader', merge_vader_report())
    await harness.write_report(started, 'uncle-bob', uncle_bob_report())
    view_of(await harness.call('review_add', {'run_id': started.run_id, 'persona': 'merge-vader'}))
    view_of(await harness.call('review_add', {'run_id': started.run_id, 'persona': 'uncle-bob'}))
    return started


class TestListedTools:
    @listed_tool_cases()
    async def test_tool_carries_title_hints_and_review_icon(
        self, server_harness: ServerHarness, name: str, title: str, annotations: ToolAnnotations
    ) -> None:
        server = server_harness.create_server(create_catalog())
        async with Client(server) as client:
            listed = {tool.name: tool for tool in (await client.list_tools()).tools}

        assert (listed[name].title, listed[name].annotations) == (title, annotations)
        assert listed[name].icons == [load_icon('review')]


class TestReviewStart:
    async def test_all_fields_given_ask_no_form_and_create_the_run_directory(
        self, harness: ReviewHarness
    ) -> None:
        answerer = RecordingAnswerer(answers={})

        view = view_of(await harness.call('review_start', dict(ALL_ANSWERED), answerer))

        run_id = view['run_id']
        directory = f'.mightymodels/.runtime/reviews/{run_id}'
        assert view['text'] == (
            f'run {run_id} at {directory}\n'
            'standard review: merge-vader on opus, uncle-bob on opus\n'
        )
        assert answerer.asked == []
        assert await anyio.Path(harness.server.repository, directory).is_dir()

    async def test_form_holds_only_the_omitted_questions(self, harness: ReviewHarness) -> None:
        answerer = RecordingAnswerer(answers={'emphasis': 'maintainability'})
        arguments = {'scope': 'diff', 'depth': 'quick'}

        view = view_of(await harness.call('review_start', arguments, answerer))

        assert answerer.asked == [frozenset({'emphasis'})]
        assert view['text'].endswith('quick review: uncle-bob on sonnet\n')

    async def test_nothing_given_asks_all_three_questions(self, harness: ReviewHarness) -> None:
        answerer = RecordingAnswerer(answers=ALL_ANSWERED)

        view_of(await harness.call('review_start', {}, answerer))

        assert answerer.asked == [frozenset({'scope', 'depth', 'emphasis'})]

    @unanswered_action_cases()
    async def test_unanswered_form_returns_the_needs_input_text(
        self, harness: ReviewHarness, action: FormAction
    ) -> None:
        answerer = RecordingAnswerer(answers={}, action=action)
        arguments = {'scope': 'diff', 'depth': 'quick'}

        view = view_of(await harness.call('review_start', arguments, answerer))

        assert view['text'] == EMPHASIS_FORM
        assert view['run_id'] is None
        assert harness.git_calls == []
        listing = view_of(await harness.call('review_list', {}))
        assert listing['text'] == 'no review runs\n'

    async def test_asks_git_only_for_head(self, harness: ReviewHarness) -> None:
        await harness.start()

        assert harness.git_calls == ['resolve_head']

    async def test_scope_needing_a_base_is_refused_without_one(
        self, harness: ReviewHarness
    ) -> None:
        result = await harness.call('review_start', {**ALL_ANSWERED, 'scope': 'branch'})

        assert result.is_error
        assert 'branch scope needs base' in str(result.content)

    async def test_ticket_scope_records_the_staged_ticket(self, harness: ReviewHarness) -> None:
        arguments = {'scope': 'ticket', 'slug': SLUG, 'base': 'main'}

        started = await harness.start(**arguments)

        assert started.directory.startswith(f'.mightymodels/{SLUG}/review/')

    async def test_base_with_a_leading_dash_is_refused_before_any_git_call(
        self, harness: ReviewHarness
    ) -> None:
        arguments = {**ALL_ANSWERED, 'scope': 'branch', 'base': '--output=x'}

        result = await harness.call('review_start', arguments)

        assert result.is_error
        assert "'--output=x' is not a plain revision name" in str(result.content)
        assert harness.git_calls == []


class TestReviewOverride:
    async def test_names_the_heavier_reviewer_and_its_effort(
        self, harness: ReviewHarness, started: StartedRun
    ) -> None:
        view = view_of(await harness.call('review_override', {'run_id': started.run_id}))

        assert view['text'] == (
            f'run {started.run_id}: merge-vader on fable\ndispatch it with effort high\n'
        )
        assert harness.git_calls == []


class TestReviewAdd:
    async def test_reads_each_persona_report_from_the_run_directory(
        self, harness: ReviewHarness, started: StartedRun
    ) -> None:
        await harness.write_report(started, 'merge-vader', merge_vader_report())
        await harness.write_report(started, 'uncle-bob', uncle_bob_report())

        first = view_of(
            await harness.call('review_add', {'run_id': started.run_id, 'persona': 'merge-vader'})
        )
        second = view_of(
            await harness.call('review_add', {'run_id': started.run_id, 'persona': 'uncle-bob'})
        )

        assert first['text'] == '1 findings in, 1 recorded: F1\n'
        assert second['text'] == '1 findings in, 1 recorded: F2\n'
        assert harness.git_calls == []

    async def test_missing_report_is_refused_with_its_path(
        self, harness: ReviewHarness, started: StartedRun
    ) -> None:
        result = await harness.call(
            'review_add', {'run_id': started.run_id, 'persona': 'uncle-bob'}
        )

        assert result.is_error
        assert (
            f'no uncle-bob report at {started.directory}/{REPORT_NAMES["uncle-bob"]}; '
            'the reviewer writes it there first'
        ) in str(result.content)

    async def test_symlinked_report_is_refused_as_missing(
        self, harness: ReviewHarness, started: StartedRun
    ) -> None:
        target = anyio.Path(harness.server.repository, 'elsewhere.md')
        await target.write_text(uncle_bob_report(), encoding='utf-8')
        link = anyio.Path(harness.server.repository, started.directory, REPORT_NAMES['uncle-bob'])
        await link.symlink_to(target)

        result = await harness.call(
            'review_add', {'run_id': started.run_id, 'persona': 'uncle-bob'}
        )

        assert result.is_error
        assert 'no uncle-bob report at' in str(result.content)


class TestReviewGate:
    async def test_lists_the_findings_in_gate_order(
        self, harness: ReviewHarness, reported: StartedRun
    ) -> None:
        view = view_of(await harness.call('review_gate', {'run_id': reported.run_id}))

        assert view['text'] == (
            'F1\tHigh security\t[MV-1]\tsrc/a.py:10\tUnchecked input\tundecided\n'
            'F2\tMedium quality\t[UB-1]\tsrc/b.py:5-9\tMixed duties\tundecided\n'
        )
        assert harness.git_calls == []


class TestReviewReport:
    async def test_full_report_carries_the_verdict(
        self, harness: ReviewHarness, reported: StartedRun
    ) -> None:
        view = view_of(await harness.call('review_report', {'run_id': reported.run_id}))

        assert view['verdict'] == 'BLOCK'
        assert view['text'].startswith('# Review report\n\n**Verdict: BLOCK**\n')
        assert '### F1 | High security | Unchecked input\n' in view['text']
        assert harness.git_calls == []

    async def test_comment_shape_is_the_short_form(
        self, harness: ReviewHarness, reported: StartedRun
    ) -> None:
        arguments = {'run_id': reported.run_id, 'shape': 'comment'}

        view = view_of(await harness.call('review_report', arguments))

        assert view['text'].startswith('## Review\n\n**Verdict: BLOCK**\n')
        assert '- F1 (High security, undecided): Unchecked input. `src/a.py:10`\n' in view['text']


class TestReviewList:
    async def test_lists_each_run_with_its_findings_and_verdict(
        self, harness: ReviewHarness, reported: StartedRun
    ) -> None:
        view = view_of(await harness.call('review_list', {}))

        assert view['text'] == f'{reported.run_id}\t-\tstandard\t2 findings\tBLOCK\n'
        assert harness.git_calls == []


class TestUnknownRun:
    @unknown_run_cases()
    async def test_is_refused_with_core_message(
        self, harness: ReviewHarness, name: str, extra: dict[str, str]
    ) -> None:
        result = await harness.call(name, {'run_id': UNKNOWN_RUN, **extra})

        assert result.is_error
        assert f'no review run {UNKNOWN_RUN}; start one first' in str(result.content)
