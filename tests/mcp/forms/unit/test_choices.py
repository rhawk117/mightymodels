from typing import TYPE_CHECKING

import pytest
from mcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
    render_elicitation_schema,
)
from mcp.server.mcpserver.resolve import Elicit
from mcp_types._v2025_11_25 import TitledSingleSelectEnumSchema
from mightymodels_mcp.forms.choices import (
    ChoiceRound,
    TextQuestion,
    answers_of,
    complete_request,
)
from mightymodels_mcp.forms.needs_input import NEEDS_INPUT, needs_input_text
from mightymodels_mcp.server.requests import RequestModel
from pydantic import BaseModel, ValidationError

from tests.mcp.forms.form_probes import DEPTH, MODE, REVIEW_ROUND, ChainRequest

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_mcp.forms.choices import ChoiceOutcome


def unanswered_outcome_cases() -> pytest.MarkDecorator:
    outcomes: list[ParameterSet] = [
        pytest.param(DeclinedElicitation(), id='decline'),
        pytest.param(CancelledElicitation(), id='cancel'),
    ]
    return pytest.mark.parametrize('outcome', outcomes)


class TestChoiceRound:
    bare_request = ChainRequest(slug='probe-ticket')
    moded_request = ChainRequest(slug='probe-ticket', mode='quick')
    full_request = ChainRequest(slug='probe-ticket', mode='quick', depth='diff')

    def render_properties(self, round_: ChoiceRound) -> dict[str, dict[str, object]]:
        return render_elicitation_schema(round_.create_schema())['properties']

    def test_each_question_renders_as_a_titled_single_select(self) -> None:
        properties = self.render_properties(REVIEW_ROUND)

        for question in (MODE, DEPTH):
            rendered = TitledSingleSelectEnumSchema.model_validate(properties[question.argument])
            pairs = [(item.const, item.title) for item in rendered.one_of]
            assert pairs == [(choice.value, choice.title) for choice in question.choices]
            assert rendered.title == question.title
            assert rendered.description == question.description

    def test_round_holds_only_the_omitted_fields(self) -> None:
        omitted = REVIEW_ROUND.omitted_by(self.moded_request)

        assert list(self.render_properties(omitted)) == ['depth']

    def test_omitted_fields_are_asked(self) -> None:
        asked = REVIEW_ROUND.omitted_by(self.bare_request).ask()

        assert isinstance(asked, Elicit)
        assert asked.message == REVIEW_ROUND.message

    def test_round_with_nothing_omitted_asks_nothing(self) -> None:
        asked = REVIEW_ROUND.omitted_by(self.full_request).ask()

        assert isinstance(asked, BaseModel)
        assert asked.model_dump() == {}

    def test_answer_outside_the_choices_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            REVIEW_ROUND.create_schema().model_validate({'mode': 'reckless', 'depth': 'diff'})

    def test_accepted_answers_complete_the_request(self) -> None:
        schema = REVIEW_ROUND.omitted_by(self.moded_request).create_schema()
        outcome: ChoiceOutcome = AcceptedElicitation(data=schema.model_validate({'depth': 'diff'}))

        assert complete_request(self.moded_request, outcome) == self.full_request

    @unanswered_outcome_cases()
    def test_unanswered_round_has_no_answers(self, outcome: ChoiceOutcome) -> None:
        assert answers_of(outcome) is None
        assert complete_request(self.bare_request, outcome) is None


class NamedRequest(RequestModel):
    mode: str | None = None
    label: str | None = None


NAME = TextQuestion(
    argument='label_text', answers='label', title='Label', description='Name the label.'
)
NAMED_ROUND = ChoiceRound(message='Name it', questions=(MODE,), texts=(NAME,))


class TestTextQuestion:
    def render_properties(self, round_: ChoiceRound) -> dict[str, dict[str, object]]:
        return render_elicitation_schema(round_.create_schema())['properties']

    def test_text_renders_as_an_optional_string(self) -> None:
        rendered = render_elicitation_schema(NAMED_ROUND.create_schema())

        assert rendered['properties']['label_text']['type'] == 'string'
        assert rendered['required'] == ['mode']

    def test_text_is_asked_only_when_its_field_is_omitted(self) -> None:
        omitted = NAMED_ROUND.omitted_by(NamedRequest(mode='quick'))
        answered = NAMED_ROUND.omitted_by(NamedRequest(mode='quick', label='x'))

        assert list(self.render_properties(omitted)) == ['label_text']
        asked = answered.ask()

        assert isinstance(asked, BaseModel)
        assert asked.model_dump() == {}

    def test_text_round_asks_when_only_text_is_omitted(self) -> None:
        asked = NAMED_ROUND.omitted_by(NamedRequest(mode='quick')).ask()

        assert isinstance(asked, Elicit)

    def test_unanswered_text_is_none(self) -> None:
        schema = NAMED_ROUND.create_schema()

        assert schema.model_validate({'mode': 'quick'}).model_dump() == {
            'mode': 'quick',
            'label_text': None,
        }

    def test_choice_questions_stay_choice_only(self) -> None:
        assert NAMED_ROUND.questions == (MODE,)


class TestNeedsInputText:
    def test_text_names_each_question_its_choices_and_argument(self) -> None:
        text = needs_input_text(REVIEW_ROUND.questions)

        assert text == (
            f'{NEEDS_INPUT}\n'
            'Which review mode?\nchoices: quick, deep\npass: mode\n'
            'Which depth?\nchoices: diff, branch\npass: depth\n'
        )
