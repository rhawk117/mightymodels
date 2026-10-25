"""Register tools that take one request model and the context, with complete metadata.

The tool is built from the definition's models rather than from the handler's signature, so
the handler's annotations are never evaluated at runtime. Core refusals (`StateError`) reach
the client as tool errors carrying core's message; any other exception stays a crash the SDK
reports without its text.
"""

import inspect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata
from mightymodels_core.primitives import StateError
from pydantic import BaseModel

from .dependencies import ServerDependencies
from .requests import RequestModel

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.types import Icon, ToolAnnotations

type ToolContext = Context[ServerDependencies, Any]
type ToolHandler[R: RequestModel, V: BaseModel] = Callable[[R, ToolContext], Awaitable[V]]

CONTEXT_ARGUMENT = 'ctx'
ANNOTATION_HINTS = ('read_only_hint', 'destructive_hint', 'idempotent_hint', 'open_world_hint')


class ToolRegistrationError(Exception):
    pass


class MissingToolTitleError(ToolRegistrationError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'tool {name!r} has no title')


class IncompleteToolAnnotationsError(ToolRegistrationError):
    def __init__(self, *, name: str, missing: tuple[str, ...]) -> None:
        self.name = name
        self.missing = missing
        super().__init__(f'tool {name!r} does not set {", ".join(missing)}')


class MissingToolIconError(ToolRegistrationError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'tool {name!r} has no icon')


class DuplicateToolNameError(ToolRegistrationError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'a tool named {name!r} is already registered')


type ToolDefinitionProblem = (
    MissingToolTitleError | IncompleteToolAnnotationsError | MissingToolIconError
)


@dataclass(slots=True, kw_only=True, frozen=True)
class ToolDefinition[R: RequestModel, V: BaseModel]:
    name: str
    title: str | None
    annotations: ToolAnnotations | None
    icon: Icon | None
    request_model: type[R]
    result_model: type[V]
    handler: ToolHandler[R, V]

    @property
    def description(self) -> str:
        return inspect.getdoc(self.handler) or ''

    @property
    def icons(self) -> list[Icon] | None:
        return None if self.icon is None else [self.icon]


@dataclass(slots=True, kw_only=True, frozen=True)
class ToolDefinitionPolicy[R: RequestModel, V: BaseModel]:
    definition: ToolDefinition[R, V]

    @property
    def has_title(self) -> bool:
        return bool(self.definition.title)

    @property
    def unset_hints(self) -> tuple[str, ...]:
        annotations = self.definition.annotations
        if annotations is None:
            return ANNOTATION_HINTS

        return tuple(hint for hint in ANNOTATION_HINTS if getattr(annotations, hint) is None)

    def get_definition_problem(self) -> ToolDefinitionProblem | None:
        name = self.definition.name
        if not self.has_title:
            return MissingToolTitleError(name=name)

        if unset_hints := self.unset_hints:
            return IncompleteToolAnnotationsError(name=name, missing=unset_hints)

        if self.definition.icon is None:
            return MissingToolIconError(name=name)

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusalTranslatingHandler[R: RequestModel, V: BaseModel]:
    handler: ToolHandler[R, V]

    async def run(self, request: R, ctx: ToolContext) -> V:
        try:
            return await self.handler(request, ctx)
        except StateError as refusal:
            raise ToolError(str(refusal)) from refusal


def create_tool[R: RequestModel, V: BaseModel](definition: ToolDefinition[R, V]) -> Tool:
    request_model = definition.request_model
    translator = RefusalTranslatingHandler(handler=definition.handler)
    return Tool(
        fn=translator.run,
        name=definition.name,
        title=definition.title,
        description=definition.description,
        parameters=request_model.model_json_schema(by_alias=True),
        fn_metadata=FuncMetadata(arg_model=request_model, output_model=definition.result_model),
        is_async=True,
        context_kwarg=CONTEXT_ARGUMENT,
        annotations=definition.annotations,
        icons=definition.icons,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ToolCatalog:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register[R: RequestModel, V: BaseModel](self, definition: ToolDefinition[R, V]) -> Self:
        if problem := ToolDefinitionPolicy(definition=definition).get_definition_problem():
            raise problem

        if definition.name in self.tools:
            raise DuplicateToolNameError(name=definition.name)

        self.tools[definition.name] = create_tool(definition)
        return self

    def list_tools(self) -> list[Tool]:
        return list(self.tools.values())
