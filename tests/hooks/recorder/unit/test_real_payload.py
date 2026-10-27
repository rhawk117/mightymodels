"""Pins the recorder's payload keys against real AskUserQuestion results.

That the hook's `tool_response` equals the transcript's `toolUseResult` is inferred, not checked.
"""

from mightymodels_hooks.ask_recorder import answers_of
from mightymodels_hooks.recorder_state import Answered

from tests.hooks.recorder import real_payloads as real
from tests.hooks.recorder.recorder_builders import real_payload


class TestRealAskUserQuestionResults:
    def test_each_plain_answer_is_one_decision_with_the_verbatim_label(self) -> None:
        assert answers_of(real_payload(real.PLAIN)) == [
            Answered(question=real.PLAIN_QUESTION, answer='Not sure, have scouts find it'),
            Answered(
                question=real.PLAIN_TOOLS_QUESTION, answer='One MCP tool per action (Recommended)'
            ),
        ]

    def test_an_option_preview_is_not_a_note(self) -> None:
        assert answers_of(real_payload(real.PREVIEW)) == [
            Answered(question=real.PREVIEW_QUESTION, answer='Port whole module (Recommended)')
        ]

    def test_the_annotation_notes_are_the_note(self) -> None:
        assert answers_of(real_payload(real.NOTES)) == [
            Answered(question=real.NOTES_QUESTION, answer="I don't know", note=real.NOTES_TEXT)
        ]

    def test_an_afk_timeout_gives_nothing(self) -> None:
        assert answers_of(real_payload(real.AFK)) == []

    def test_a_multi_select_answer_is_one_string(self) -> None:
        decisions = answers_of(real_payload(real.MULTI))
        assert [decision.question for decision in decisions] == [
            real.MULTI_GATE_QUESTION,
            real.MULTI_E48_QUESTION,
            real.MULTI_SPLIT_QUESTION,
        ]
        assert decisions[2].answer == real.MULTI_SPLIT_ANSWER
        assert all(decision.note is None for decision in decisions)
