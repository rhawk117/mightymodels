from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from mcp import Client
from mcp.types import ToolAnnotations
from mightymodels_mcp.forms.needs_input import NEEDS_INPUT
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.icons import load_icon

from tests.mcp.review.review_harness import DisposeAnswerer, create_review_harness
from tests.mcp.server.server_harness import view_of

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.mcp.review.review_harness import ReviewHarness, StartedRun
    from tests.mcp.server.server_harness import ServerHarness
    from tests.mcp.ticket.ticket_harness import FormAction

REPLACES = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False
)
UNKNOWN_RUN = '20200101-000000'
FIRST_PAGE = tuple(f'finding_{position}' for position in range(1, 11))
PAGE_KEYS = ', '.join(f'F{number}' for number in range(1, 11))
UNANSWERED_PAGE = (
    f'{NEEDS_INPUT}\nWhat should happen to {PAGE_KEYS}? accept-risk and dismiss need a reason.\n'
    'choices: fix, defer, accept-risk, dismiss\n'
    'pass: decisions {"F…": {"decision": <choice>, "reason": "<why>"}}\n'
)


def reasons_fields(count: int) -> tuple[str, ...]:
    return tuple(
        name
        for position in range(1, count + 1)
        for name in (f'decision_{position}', f'reason_{position}')
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class UnansweredRound:
    name: str
    actions: tuple[FormAction, ...]
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


@dataclass(slots=True, kw_only=True, frozen=True)
class Refusal:
    name: str
    tool: str
    arguments: dict[str, Any]
    message: str
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


def listed_tool_cases() -> pytest.MarkDecorator:
    tools: list[ParameterSet] = [
        pytest.param('review_dispose', "Decide a review's findings", REPLACES, id='dispose'),
        pytest.param('review_resolve', 'Resolve a review finding', REPLACES, id='resolve'),
    ]
    return pytest.mark.parametrize(('name', 'title', 'annotations'), tools)


def dispose_unanswered_round_cases() -> pytest.MarkDecorator:
    rounds = [
        UnansweredRound(name='page-declined', actions=('decline',)),
        UnansweredRound(name='page-cancelled', actions=('cancel',)),
        UnansweredRound(name='reasons-declined', actions=('accept', 'decline')),
        UnansweredRound(name='reasons-cancelled', actions=('accept', 'cancel')),
    ]
    return pytest.mark.parametrize('unanswered', [case.param for case in rounds])


def dispose_refusal_cases() -> pytest.MarkDecorator:
    unknown_run = Refusal(
        name='unknown-run',
        tool='review_dispose',
        arguments={'run_id': UNKNOWN_RUN},
        message=f'no review run {UNKNOWN_RUN}; start one first',
    )
    reasonless = [
        Refusal(
            name=decision,
            tool='review_dispose',
            arguments={'decisions': {'F1': {'decision': decision, 'reason': '  '}}, 'by': 'owner'},
            message=f'F1: {decision} needs a reason; nothing was written',
        )
        for decision in ('accept-risk', 'dismiss')
    ]
    refusals = [unknown_run, *reasonless]
    return pytest.mark.parametrize('refusal', [case.param for case in refusals])


def resolve_refusal_cases() -> pytest.MarkDecorator:
    refusals = [
        Refusal(
            name='fixed-without-commit',
            tool='review_resolve',
            arguments={'finding': 'F1', 'result': 'fixed'},
            message='F1: fixed needs commit',
        ),
        Refusal(
            name='not-chosen-for-fix',
            tool='review_resolve',
            arguments={'finding': 'F2', 'result': 'fixed', 'commit': 'abc1234'},
            message='F2: only a finding the user chose to fix is resolved',
        ),
        Refusal(
            name='unknown-run',
            tool='review_resolve',
            arguments={'run_id': UNKNOWN_RUN, 'finding': 'F1', 'result': 'fixed'},
            message=f'no review run {UNKNOWN_RUN}; start one first',
        ),
    ]
    return pytest.mark.parametrize('refusal', [case.param for case in refusals])


@pytest.fixture
async def harness(server_harness: ServerHarness) -> ReviewHarness:
    return await create_review_harness(server_harness)


@pytest.fixture
async def eleven(harness: ReviewHarness) -> StartedRun:
    return await harness.start_with_findings(11)


@pytest.fixture
async def chosen(harness: ReviewHarness) -> StartedRun:
    started = await harness.start_with_findings(2)
    decisions = {'F1': {'decision': 'fix'}, 'F2': {'decision': 'defer'}}
    arguments = {'run_id': started.run_id, 'decisions': decisions, 'by': 'owner'}
    view_of(await harness.call('review_dispose', arguments))
    return started


async def gate_decisions(harness: ReviewHarness, started: StartedRun) -> list[str]:
    view = view_of(await harness.call('review_gate', {'run_id': started.run_id}))
    return [line.rpartition('\t')[2] for line in view['text'].splitlines()]


async def refusal_text(harness: ReviewHarness, started: StartedRun, refusal: Refusal) -> str:
    result = await harness.call(refusal.tool, {'run_id': started.run_id, **refusal.arguments})
    assert result.is_error
    return str(result.content)


class TestListedTools:
    @listed_tool_cases()
    async def test_tool_carries_title_hints_and_review_icon(
        self,
        server_harness: ServerHarness,
        name: str,
        title: str,
        annotations: ToolAnnotations,
    ) -> None:
        server = server_harness.create_server(create_catalog())
        async with Client(server) as client:
            listed = {tool.name: tool for tool in (await client.list_tools()).tools}

        assert (listed[name].title, listed[name].annotations) == (title, annotations)
        assert listed[name].icons == [load_icon('review')]


class TestReviewDispose:
    some_checked = frozenset({1, 2, 3})
    all_checked = frozenset(range(1, 11))

    async def test_first_call_shows_ten_boxes_then_reasons_for_the_unchecked(
        self, harness: ReviewHarness, eleven: StartedRun
    ) -> None:
        answerer = DisposeAnswerer(checked=self.some_checked)

        view = view_of(await harness.call('review_dispose', {'run_id': eleven.run_id}, answerer))

        assert answerer.asked == [FIRST_PAGE, reasons_fields(7)]
        assert view['text'] == '10 dispositions recorded; undecided: F11\n'
        assert harness.git_calls == []

    async def test_checked_record_fix_and_unchecked_their_decision(
        self, harness: ReviewHarness, eleven: StartedRun
    ) -> None:
        answerer = DisposeAnswerer(checked=self.some_checked, decision='dismiss')

        view_of(await harness.call('review_dispose', {'run_id': eleven.run_id}, answerer))

        expected = ['fix'] * 3 + ['dismiss'] * 7 + ['undecided']
        assert await gate_decisions(harness, eleven) == expected

    async def test_second_call_takes_the_last_finding(
        self, harness: ReviewHarness, eleven: StartedRun
    ) -> None:
        arguments = {'run_id': eleven.run_id}
        view_of(await harness.call('review_dispose', arguments, DisposeAnswerer()))
        answerer = DisposeAnswerer(checked=frozenset({1}))

        view = view_of(await harness.call('review_dispose', arguments, answerer))

        assert answerer.asked == [('finding_1',)]
        assert view['text'] == '1 dispositions recorded\n'

    async def test_every_box_checked_asks_no_reasons_round(
        self, harness: ReviewHarness, eleven: StartedRun
    ) -> None:
        answerer = DisposeAnswerer(checked=self.all_checked)

        view_of(await harness.call('review_dispose', {'run_id': eleven.run_id}, answerer))

        assert answerer.asked == [FIRST_PAGE]

    @dispose_unanswered_round_cases()
    async def test_unanswered_round_records_nothing(
        self, harness: ReviewHarness, eleven: StartedRun, unanswered: UnansweredRound
    ) -> None:
        answerer = DisposeAnswerer(checked=self.some_checked, actions=unanswered.actions)

        view = view_of(await harness.call('review_dispose', {'run_id': eleven.run_id}, answerer))

        assert view['text'] == UNANSWERED_PAGE
        assert await gate_decisions(harness, eleven) == ['undecided'] * 11

    async def test_given_decisions_ask_no_form(
        self, harness: ReviewHarness, eleven: StartedRun
    ) -> None:
        answerer = DisposeAnswerer()
        decisions = {'F1': {'decision': 'fix'}, 'F2': {'decision': 'dismiss', 'reason': 'noise'}}
        arguments = {'run_id': eleven.run_id, 'decisions': decisions, 'by': 'owner'}

        view = view_of(await harness.call('review_dispose', arguments, answerer))

        undecided = ', '.join(f'F{number}' for number in range(3, 12))
        assert view['text'] == f'2 dispositions recorded; undecided: {undecided}\n'
        assert answerer.asked == []

    async def test_nothing_undecided_asks_nothing(
        self, harness: ReviewHarness, chosen: StartedRun
    ) -> None:
        answerer = DisposeAnswerer()

        view = view_of(await harness.call('review_dispose', {'run_id': chosen.run_id}, answerer))

        assert view['text'] == '0 dispositions recorded\n'
        assert answerer.asked == []

    async def test_same_decisions_twice_record_the_same_values(
        self, harness: ReviewHarness, eleven: StartedRun
    ) -> None:
        decisions = {'F1': {'decision': 'fix'}, 'F2': {'decision': 'dismiss', 'reason': 'noise'}}
        arguments = {'run_id': eleven.run_id, 'decisions': decisions, 'by': 'owner'}
        view_of(await harness.call('review_dispose', arguments))
        first = await gate_decisions(harness, eleven)

        second = await harness.call('review_dispose', arguments)

        assert not second.is_error
        assert await gate_decisions(harness, eleven) == first

    @dispose_refusal_cases()
    async def test_refused_with_core_message(
        self, harness: ReviewHarness, eleven: StartedRun, refusal: Refusal
    ) -> None:
        assert refusal.message in await refusal_text(harness, eleven, refusal)


class TestReviewResolve:
    async def test_fixed_with_a_commit_is_recorded(
        self, harness: ReviewHarness, chosen: StartedRun
    ) -> None:
        arguments = {
            'run_id': chosen.run_id,
            'finding': 'F1',
            'result': 'fixed',
            'commit': 'abc1234',
        }

        view = view_of(await harness.call('review_resolve', arguments))

        assert view['text'] == 'F1 fixed\n'
        assert harness.git_calls == []

    async def test_same_resolution_twice_records_the_same_outcome(
        self, harness: ReviewHarness, chosen: StartedRun
    ) -> None:
        arguments = {
            'run_id': chosen.run_id,
            'finding': 'F1',
            'result': 'fixed',
            'commit': 'abc1234',
        }
        first = view_of(await harness.call('review_resolve', arguments))

        second = await harness.call('review_resolve', arguments)

        assert not second.is_error
        assert view_of(second)['text'] == first['text'] == 'F1 fixed\n'

    @resolve_refusal_cases()
    async def test_refused_with_core_message(
        self, harness: ReviewHarness, chosen: StartedRun, refusal: Refusal
    ) -> None:
        assert refusal.message in await refusal_text(harness, chosen, refusal)
