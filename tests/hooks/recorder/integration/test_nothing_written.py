from typing import TYPE_CHECKING

import pytest

from tests.hooks.recorder.recorder_builders import ask_payload, two_answers

if TYPE_CHECKING:
    from tests.hooks.recorder.recorder_builders import RecorderHarness


def silent_payloads() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'payload',
        [
            pytest.param({**ask_payload(two_answers()), 'session_id': None}, id='no-session'),
            pytest.param(ask_payload(None), id='no-answers'),
            pytest.param(ask_payload('Redis'), id='answers-not-an-object'),
            pytest.param(ask_payload(two_answers(), afkTimeoutMs=500), id='afk'),
        ],
    )


class TestNothingWritten:
    async def test_a_session_with_no_pointer_writes_nothing(self, harness: RecorderHarness) -> None:
        ticket_id = await harness.stage_ticket()
        output = await harness.record({**ask_payload(two_answers()), 'session_id': 'other'})
        assert output is None
        assert await harness.ticket_decisions(ticket_id) == ()
        assert harness.stderr.getvalue() == ''

    async def test_a_closed_ticket_writes_nothing(self, harness: RecorderHarness) -> None:
        ticket_id = await harness.stage_ticket(closed=True)
        output = await harness.record(ask_payload(two_answers()))
        assert output is None
        assert await harness.ticket_decisions(ticket_id) == ()

    @silent_payloads()
    async def test_a_payload_the_recorder_cannot_use_writes_nothing(
        self, harness: RecorderHarness, payload: dict[str, object]
    ) -> None:
        ticket_id = await harness.stage_ticket()
        output = await harness.record(payload)
        assert output is None
        assert await harness.ticket_decisions(ticket_id) == ()
        assert harness.stderr.getvalue() == ''

    async def test_an_unknown_investigation_writes_nothing_and_says_so(
        self, harness: RecorderHarness
    ) -> None:
        await harness.stage_ticket()
        await harness.point('investigation', 'missing-one')
        output = await harness.record(ask_payload(two_answers()))
        assert output is None
        assert harness.stderr.getvalue().startswith('mightymodels-hooks: ask-recorder:')
