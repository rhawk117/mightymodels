from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mcp.types import ToolAnnotations
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import (
    ANNOTATION_HINTS,
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
    unset_hints = [unset_hint_definition(hint) for hint in ANNOTATION_HINTS]
    cases = [untitled, blank_title, unannotated, iconless, *unset_hints]
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
        assert refused.value.missing == ANNOTATION_HINTS

    def test_duplicate_name_is_refused(self, catalog: ToolCatalog) -> None:
        catalog.register(create_note_definition())
        with pytest.raises(DuplicateToolNameError):
            catalog.register(create_note_definition())
        assert len(catalog.list_tools()) == 1
