from typing import TYPE_CHECKING

from tests.hooks.recorder.recorder_builders import (
    FIRST,
    SECOND,
    SECRET,
    ask_payload,
    two_answers,
)

if TYPE_CHECKING:
    from tests.hooks.recorder.recorder_builders import RecorderHarness


class TestInvestigationDecisions:
    async def test_two_questions_yield_two_user_decisions_in_round_one(
        self, harness: RecorderHarness
    ) -> None:
        key = await harness.start_investigation()
        output = await harness.record(ask_payload(two_answers()))
        records = await harness.ledger(key)
        assert output is None
        assert [(record.kind, record.source, record.round) for record in records] == [
            ('decision', 'user', 1),
            ('decision', 'user', 1),
        ]
        assert records[1].text == f'{SECOND}\nAnswer: Lint, Tests'
        assert harness.stderr.getvalue() == ''

    async def test_a_note_and_a_response_are_in_the_text_and_a_secret_is_redacted(
        self, harness: RecorderHarness
    ) -> None:
        key = await harness.start_investigation()
        payload = ask_payload(
            {FIRST: f'Other: {SECRET}'}, {FIRST: {'notes': 'a note'}}, response='a response'
        )
        await harness.record(payload)
        (record,) = await harness.ledger(key)
        assert record.text.startswith(f'{FIRST}\nAnswer: Other: ')
        assert SECRET not in record.text
        assert record.text.endswith('\nResponse: a response\nNote: a note')

    async def test_an_oversized_decision_is_skipped_alone(self, harness: RecorderHarness) -> None:
        key = await harness.start_investigation()
        await harness.record(ask_payload({FIRST: 'x' * 4001, SECOND: 'Redis'}))
        (record,) = await harness.ledger(key)
        assert record.text == f'{SECOND}\nAnswer: Redis'
        assert 'skipped a decision' in harness.stderr.getvalue()
