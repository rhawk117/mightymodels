"""The text a tool returns when no one answered its round.

Under `claude -p` nobody can answer, so the host declines or cancels at once. The tool then
returns this text as its normal result, naming each unanswered question, its choices and the
argument to pass, so the primary can ask in the foreground and call again.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .choices import ChoiceQuestion

NEEDS_INPUT = 'needs input: no one answered; ask the user, then call again with the argument shown'


def describe_question(question: ChoiceQuestion) -> str:
    choices = ', '.join(question.values)
    return f'{question.title}\nchoices: {choices}\npass: {question.prompt or question.argument}\n'


def needs_input_text(questions: Iterable[ChoiceQuestion]) -> str:
    return f'{NEEDS_INPUT}\n' + ''.join(map(describe_question, questions))
