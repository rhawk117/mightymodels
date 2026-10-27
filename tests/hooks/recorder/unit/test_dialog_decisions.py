import pytest
from mightymodels_hooks.ask_recorder import answers_of
from mightymodels_hooks.recorder_state import Answered, ledger_text

from tests.hooks.recorder.recorder_builders import FIRST, SECOND, ask_payload, two_answers


class TestAnswersOf:
    def test_each_answered_question_is_one_decision(self) -> None:
        assert answers_of(ask_payload(two_answers())) == [
            Answered(question=FIRST, answer='Redis'),
            Answered(question=SECOND, answer='Lint, Tests'),
        ]

    def test_the_response_and_the_questions_own_note_ride_along(self) -> None:
        payload = ask_payload(
            two_answers(),
            {FIRST: {'notes': 'cheap to run'}, 'other': {'notes': 'x'}},
            response='ok',
        )
        assert answers_of(payload)[0] == Answered(
            question=FIRST, answer='Redis', response='ok', note='cheap to run'
        )
        assert answers_of(payload)[1].note is None

    @pytest.mark.parametrize('annotations', ['text', [1], {FIRST: 'text'}, {FIRST: {'notes': 3}}])
    def test_a_malformed_annotation_gives_no_note(self, annotations: object) -> None:
        assert answers_of(ask_payload({FIRST: 'Redis'}, annotations))[0].note is None

    @pytest.mark.parametrize('answers', [None, 'Redis', ['Redis'], {}, {FIRST: 3}, {FIRST: ''}])
    def test_missing_or_malformed_answers_give_nothing(self, answers: object) -> None:
        assert answers_of(ask_payload(answers)) == []

    def test_an_afk_timeout_gives_nothing(self) -> None:
        assert answers_of(ask_payload(two_answers(), afkTimeoutMs=1000)) == []

    @pytest.mark.parametrize('response', [None, 3, ''])
    def test_a_blank_response_is_dropped(self, response: object) -> None:
        assert answers_of(ask_payload({FIRST: 'Redis'}, response=response))[0].response is None

    def test_a_payload_without_a_tool_response_gives_nothing(self) -> None:
        assert answers_of({'session_id': 's'}) == []


class TestLedgerText:
    def test_the_lines_are_the_question_then_the_labeled_answer(self) -> None:
        assert ledger_text(Answered(question='Q?', answer='A')) == 'Q?\nAnswer: A'

    def test_the_response_and_note_follow_when_present(self) -> None:
        answered = Answered(question='Q?', answer='A, B', response='R', note='N')
        assert ledger_text(answered) == 'Q?\nAnswer: A, B\nResponse: R\nNote: N'
