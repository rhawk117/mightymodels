from typing import TYPE_CHECKING

import pytest
from mightymodels_mcp.forms.needs_input import NEEDS_INPUT

from tests.mcp.investigation.investigation_harness import (
    KNOWN_ENTRY,
    OPEN_ENTRY,
    TARGET,
    create_investigation_harness,
)
from tests.mcp.server.server_harness import view_of
from tests.mcp.ticket.ticket_harness import RecordingAnswerer

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.mcp.investigation.investigation_harness import InvestigationHarness
    from tests.mcp.server.server_harness import ServerHarness
    from tests.mcp.ticket.ticket_harness import FormAction

KIND_FORM = (
    f'{NEEDS_INPUT}\nWhat kind of target is this?\n'
    'choices: behavior, claim, research, change\npass: kind\n'
)
UNKNOWN = '20200101-nothing'


def unanswered_action_cases() -> pytest.MarkDecorator:
    actions: list[ParameterSet] = [
        pytest.param('decline', id='decline'),
        pytest.param('cancel', id='cancel'),
    ]
    return pytest.mark.parametrize('action', actions)


@pytest.fixture
def harness(server_harness: ServerHarness) -> InvestigationHarness:
    return create_investigation_harness(server_harness)


@pytest.fixture
async def started(harness: InvestigationHarness) -> str:
    await harness.commit('first')
    return await harness.start()


@pytest.fixture
async def recorded(harness: InvestigationHarness) -> None:
    await harness.record_repository()


class TestInvestigationStart:
    async def test_with_a_kind_asks_no_form_and_returns_the_id(
        self, harness: InvestigationHarness
    ) -> None:
        answerer = RecordingAnswerer(answers={})

        view = view_of(
            await harness.call('investigation_start', {'target': TARGET, 'kind': 'claim'}, answerer)
        )

        assert answerer.asked == []
        assert view['text'].startswith(f'started {view["investigation_id"]}\n')
        assert view['investigation_id'].endswith('queue-drains-slowly')

    async def test_without_a_kind_asks_exactly_the_kind(
        self, harness: InvestigationHarness
    ) -> None:
        answerer = RecordingAnswerer(answers={'kind': 'claim'})

        view_of(await harness.call('investigation_start', {'target': TARGET}, answerer))

        assert answerer.asked == [frozenset({'kind'})]

    async def test_accepted_answer_is_the_kind_the_ledger_shows(
        self, harness: InvestigationHarness
    ) -> None:
        answerer = RecordingAnswerer(answers={'kind': 'behavior'})
        view = view_of(await harness.call('investigation_start', {'target': TARGET}, answerer))

        arguments = {'investigation_id': view['investigation_id']}
        rendered = view_of(await harness.call('investigation_render', arguments))

        assert f'Target: {TARGET} (behavior)' in rendered['text']

    @pytest.mark.usefixtures('recorded')
    @unanswered_action_cases()
    async def test_unanswered_form_returns_the_needs_input_text_and_starts_nothing(
        self, harness: InvestigationHarness, action: FormAction
    ) -> None:
        answerer = RecordingAnswerer(answers={}, action=action)

        view = view_of(await harness.call('investigation_start', {'target': TARGET}, answerer))
        listed = view_of(await harness.call('investigation_list', {}))

        assert view['text'] == KIND_FORM
        assert view['investigation_id'] is None
        assert listed['text'] == 'no investigations\n'

    async def test_asks_git_nothing(self, harness: InvestigationHarness) -> None:
        await harness.start()

        assert harness.git_calls == []


class TestInvestigationAdd:
    async def test_returns_the_saved_text_with_its_redaction_count(
        self, harness: InvestigationHarness, started: str
    ) -> None:
        arguments = {
            'investigation_id': started,
            'round': 1,
            'entries': [dict(KNOWN_ENTRY), dict(OPEN_ENTRY)],
        }

        view = view_of(await harness.call('investigation_add', arguments))

        assert view['text'].startswith(f'saved e1 e2 to {started} (0 redacted)\n')
        assert view['investigation_id'] == started

    async def test_asks_git_only_for_head(
        self, harness: InvestigationHarness, started: str
    ) -> None:
        await harness.add(started, [dict(OPEN_ENTRY)])

        assert harness.git_calls == ['resolve_head']

    async def test_unknown_investigation_is_refused(self, harness: InvestigationHarness) -> None:
        arguments = {'investigation_id': UNKNOWN, 'round': 1, 'entries': [dict(OPEN_ENTRY)]}

        assert (await harness.call('investigation_add', arguments)).is_error

    async def test_round_behind_the_latest_is_refused(
        self, harness: InvestigationHarness, started: str
    ) -> None:
        await harness.add(started, [dict(OPEN_ENTRY)], round_number=2)
        arguments = {'investigation_id': started, 'round': 1, 'entries': [dict(OPEN_ENTRY)]}

        assert (await harness.call('investigation_add', arguments)).is_error

    async def test_supersedes_naming_no_live_entry_is_refused(
        self, harness: InvestigationHarness, started: str
    ) -> None:
        entry = {**OPEN_ENTRY, 'supersedes': [99]}
        arguments = {'investigation_id': started, 'round': 1, 'entries': [entry]}

        assert (await harness.call('investigation_add', arguments)).is_error
