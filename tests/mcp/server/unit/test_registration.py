import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mcp.server.elicitation import AcceptedElicitation
from mcp.server.mcpserver.exceptions import InvalidSignature, ToolError
from mcp.server.mcpserver.resolve import Resolve
from mcp.types import ToolAnnotations
from mightymodels_core.edge import DataDirectoryMissingError
from mightymodels_mcp.server.call_log import CALL_LOGGER_NAME
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import (
    DuplicateToolNameError,
    IncompleteToolAnnotationsError,
    MissingToolIconError,
    MissingToolTitleError,
    ToolCatalog,
    ToolDefinition,
)
from mightymodels_mcp.server.requests import RequestModel
from pydantic import BaseModel

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mcp.server.mcpserver.tools import Tool
    from mightymodels_mcp.server.registration import ToolContext, ToolRegistrationError


class NoteRequest(RequestModel):
    note: str


class NoteView(BaseModel):
    note: str


@dataclass(slots=True, kw_only=True, frozen=True)
class EchoNote:
    async def run(self, request: NoteRequest, ctx: ToolContext) -> NoteView:
        """Echo the note back."""
        return NoteView(note=f'{request.note} {ctx.request_id}')


class NoteAnswer(BaseModel):
    answer: str


@dataclass(slots=True, kw_only=True, frozen=True)
class NoteAsker:
    def ask(self, request: NoteRequest) -> NoteAnswer:
        return NoteAnswer(answer=request.note.upper())

    def ask_unknown(self, unknown: str) -> NoteAnswer:
        return NoteAnswer(answer=unknown)


NOTE_RESOLVER = Resolve(NoteAsker().ask)


@dataclass(slots=True, kw_only=True, frozen=True)
class AnswerNote:
    async def run(
        self, request: NoteRequest, ctx: ToolContext, *, answer: AcceptedElicitation[NoteAnswer]
    ) -> NoteView:
        """Answer the note with the resolved value."""
        return NoteView(note=f'{request.note} {answer.data.answer} {ctx}')

    async def refuse(
        self, request: NoteRequest, ctx: ToolContext, *, answer: AcceptedElicitation[NoteAnswer]
    ) -> NoteView:
        """Be refused by core after the resolvers ran."""
        assert request, (ctx, answer)
        raise DataDirectoryMissingError(variable='VARIABLE', session_variable='SESSION')


HINT_NAMES = ('read_only_hint', 'destructive_hint', 'idempotent_hint', 'open_world_hint')
COMPLETE_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)


def create_note_definition() -> ToolDefinition[NoteRequest, NoteView]:
    return ToolDefinition(
        name='echo_note',
        title='Echo note',
        annotations=COMPLETE_ANNOTATIONS,
        icon=load_icon('server'),
        request_model=NoteRequest,
        result_model=NoteView,
        handler=EchoNote().run,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class IncompleteDefinition:
    name: str
    definition: ToolDefinition[NoteRequest, NoteView]
    refusal: type[ToolRegistrationError]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def unset_hint_definition(hint: str) -> IncompleteDefinition:
    annotations = COMPLETE_ANNOTATIONS.model_copy(update={hint: None})
    return IncompleteDefinition(
        name=f'unset-{hint}',
        definition=replace(create_note_definition(), annotations=annotations),
        refusal=IncompleteToolAnnotationsError,
    )


def incomplete_definition_cases() -> pytest.MarkDecorator:
    complete = create_note_definition()
    untitled = IncompleteDefinition(
        name='no-title',
        definition=replace(complete, title=None),
        refusal=MissingToolTitleError,
    )
    blank_title = IncompleteDefinition(
        name='blank-title',
        definition=replace(complete, title=''),
        refusal=MissingToolTitleError,
    )
    whitespace_title = IncompleteDefinition(
        name='whitespace-title',
        definition=replace(complete, title='  \t '),
        refusal=MissingToolTitleError,
    )
    unannotated = IncompleteDefinition(
        name='no-annotations',
        definition=replace(complete, annotations=None),
        refusal=IncompleteToolAnnotationsError,
    )
    iconless = IncompleteDefinition(
        name='no-icon',
        definition=replace(complete, icon=None),
        refusal=MissingToolIconError,
    )
    unset_hints = [unset_hint_definition(hint) for hint in HINT_NAMES]
    cases = [untitled, blank_title, whitespace_title, unannotated, iconless, *unset_hints]
    return pytest.mark.parametrize('incomplete', [case.param for case in cases])


class TestToolCatalog:
    @pytest.fixture
    def catalog(self) -> ToolCatalog:
        return ToolCatalog()

    def test_complete_definition_is_registered(self, catalog: ToolCatalog) -> None:
        tools = catalog.register(create_note_definition()).list_tools()
        assert [tool.name for tool in tools] == ['echo_note']

    def test_registered_tool_carries_the_metadata(self, catalog: ToolCatalog) -> None:
        tool = catalog.register(create_note_definition()).tools['echo_note']
        assert tool.title == 'Echo note'
        assert tool.description == 'Echo the note back.'
        assert tool.annotations == COMPLETE_ANNOTATIONS
        assert tool.icons == [load_icon('server')]

    def test_registered_tool_publishes_the_request_schema(self, catalog: ToolCatalog) -> None:
        tool = catalog.register(create_note_definition()).tools['echo_note']
        assert tool.parameters == NoteRequest.model_json_schema(by_alias=True)

    @incomplete_definition_cases()
    def test_incomplete_definition_is_refused(
        self, catalog: ToolCatalog, incomplete: IncompleteDefinition
    ) -> None:
        with pytest.raises(incomplete.refusal):
            catalog.register(incomplete.definition)
        assert catalog.list_tools() == []

    def test_unset_hints_are_named(self, catalog: ToolCatalog) -> None:
        unannotated = replace(create_note_definition(), annotations=None)
        with pytest.raises(IncompleteToolAnnotationsError) as refused:
            catalog.register(unannotated)
        assert refused.value.missing == HINT_NAMES

    def test_duplicate_name_is_refused(self, catalog: ToolCatalog) -> None:
        catalog.register(create_note_definition())
        with pytest.raises(DuplicateToolNameError):
            catalog.register(create_note_definition())
        assert len(catalog.list_tools()) == 1


class TestResolvingTool:
    request = NoteRequest(note='hello')

    @pytest.fixture
    def catalog(self) -> ToolCatalog:
        return ToolCatalog()

    def register_answering(self, catalog: ToolCatalog, name: str, *, refuse: bool) -> Tool:
        tool = AnswerNote()
        definition = replace(
            create_note_definition(),
            name=name,
            handler=tool.refuse if refuse else tool.run,
            resolvers={'answer': NOTE_RESOLVER},
        )
        return catalog.register(definition).tools[name]

    @pytest.fixture
    def caplog(self, caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
        caplog.set_level(logging.INFO, logger=CALL_LOGGER_NAME)
        return caplog

    def call_records(self, caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
        return [record for record in caplog.records if record.name == CALL_LOGGER_NAME]

    def test_definition_without_resolvers_resolves_nothing(self, catalog: ToolCatalog) -> None:
        tool = catalog.register(create_note_definition()).tools['echo_note']
        assert tool.resolved_params == {}
        assert tool.resolver_plans == {}

    def test_resolvers_reach_the_tool_as_full_outcomes(self, catalog: ToolCatalog) -> None:
        tool = self.register_answering(catalog, 'answer_note', refuse=False)
        ((marker, wants_union),) = tool.resolved_params.values()
        assert list(tool.resolved_params) == ['answer']
        assert marker.fn.__wrapped__ is NOTE_RESOLVER.fn
        assert wants_union
        assert len(tool.resolver_plans) == 1
        assert tool.parameters == NoteRequest.model_json_schema(by_alias=True)

    @incomplete_definition_cases()
    def test_incomplete_resolving_definition_is_refused(
        self, catalog: ToolCatalog, incomplete: IncompleteDefinition
    ) -> None:
        resolving = replace(incomplete.definition, resolvers={'answer': NOTE_RESOLVER})
        with pytest.raises(incomplete.refusal):
            catalog.register(resolving)
        assert catalog.list_tools() == []

    def test_resolver_taking_an_unknown_argument_is_refused(self, catalog: ToolCatalog) -> None:
        unknown = Resolve(NoteAsker().ask_unknown)
        definition = replace(create_note_definition(), resolvers={'answer': unknown})
        with pytest.raises(InvalidSignature):
            catalog.register(definition)

    async def test_handler_receives_the_resolved_value_and_is_recorded(
        self, catalog: ToolCatalog, caplog: pytest.LogCaptureFixture
    ) -> None:
        tool = self.register_answering(catalog, 'answer_note', refuse=False)
        answer = AcceptedElicitation(data=NoteAnswer(answer='HELLO'))

        view = await tool.fn(request=self.request, ctx='ctx', answer=answer)

        assert view == NoteView(note='hello HELLO ctx')
        (record,) = self.call_records(caplog)
        assert record.__dict__['outcome'] == 'ok'

    async def test_refusal_after_resolving_is_a_tool_error(
        self, catalog: ToolCatalog, caplog: pytest.LogCaptureFixture
    ) -> None:
        tool = self.register_answering(catalog, 'refuse_note', refuse=True)
        answer = AcceptedElicitation(data=NoteAnswer(answer='HELLO'))

        with pytest.raises(ToolError):
            await tool.fn(request=self.request, ctx='ctx', answer=answer)

        (record,) = self.call_records(caplog)
        assert record.__dict__['outcome'] == 'refused'
