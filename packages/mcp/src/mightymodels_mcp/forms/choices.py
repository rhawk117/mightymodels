"""Choice rounds: one form asking only for the fixed choices a call left out.

Each question is a titled single-select. Pydantic renders a union of titled literals as `anyOf`,
which the elicitation schema refuses, so a question's type is a plain `str` whose JSON schema
`WithJsonSchema` replaces with `oneOf` items carrying `const` and `title`, and whose value the
question itself checks. An answer outside the offered choices fails the round's model, which the
SDK reports as a tool error before the handler runs.

`ChoiceOutcome` is a plain assignment rather than a `type` alias: the SDK reads a resolver's
annotations at runtime and sees an `ElicitationResult` only one alias deep, so behind a `type`
alias a dependent resolver would get the unwrapped answer, and a declined round would abort.
"""

from dataclasses import dataclass
from typing import Annotated, Any

from mcp.server.elicitation import AcceptedElicitation, ElicitationResult
from mcp.server.mcpserver.resolve import Elicit
from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    WithJsonSchema,
    create_model,
)

from mightymodels_mcp.server.requests import NAME_LIMIT

ROUND_MODEL_NAME = 'ChoiceRound'


@dataclass(slots=True, kw_only=True, frozen=True)
class Choice:
    value: str
    title: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ChoiceQuestion:
    argument: str
    title: str
    description: str
    choices: tuple[Choice, ...]
    prompt: str | None = None

    @property
    def values(self) -> tuple[str, ...]:
        return tuple(choice.value for choice in self.choices)

    @property
    def json_schema(self) -> dict[str, Any]:
        options = [{'const': choice.value, 'title': choice.title} for choice in self.choices]
        return {'type': 'string', 'oneOf': options}

    def check(self, value: str) -> str:
        if value in self.values:
            return value

        message = f'{value!r} is not one of {", ".join(self.values)}'
        raise ValueError(message)

    def create_field(self) -> tuple[Any, Any]:
        answer = Annotated[str, AfterValidator(self.check), WithJsonSchema(self.json_schema)]
        return answer, Field(title=self.title, description=self.description)


@dataclass(slots=True, kw_only=True, frozen=True)
class TextQuestion:
    field_name: str
    answers: str
    title: str
    description: str
    max_length: int = NAME_LIMIT

    def create_field(self) -> tuple[Any, Any]:
        return str | None, Field(
            default=None,
            title=self.title,
            description=self.description,
            json_schema_extra={'maxLength': self.max_length},
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class ChoiceRound:
    message: str
    questions: tuple[ChoiceQuestion, ...]
    texts: tuple[TextQuestion, ...] = ()

    def omitted_by(self, request: BaseModel) -> ChoiceRound:
        omitted = tuple(
            question for question in self.questions if getattr(request, question.argument) is None
        )
        omitted_texts = tuple(text for text in self.texts if getattr(request, text.answers) is None)
        return ChoiceRound(message=self.message, questions=omitted, texts=omitted_texts)

    def create_schema(self) -> type[BaseModel]:
        fields: dict[str, Any] = {
            question.argument: question.create_field() for question in self.questions
        }
        fields |= {text.field_name: text.create_field() for text in self.texts}
        return create_model(ROUND_MODEL_NAME, __base__=BaseModel, **fields)

    def ask(self) -> Elicit[BaseModel] | BaseModel:
        schema = self.create_schema()
        asks_something = bool(self.questions or self.texts)
        return Elicit(self.message, schema) if asks_something else schema()


ChoiceOutcome = ElicitationResult[BaseModel]


def answers_of(outcome: ChoiceOutcome) -> dict[str, Any] | None:
    if not isinstance(outcome, AcceptedElicitation):
        return None

    return outcome.data.model_dump()
