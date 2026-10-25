"""Register tools that take one request model and the context, with complete metadata.

The tool is built from the definition's models rather than from the handler's signature, so
the handler's annotations are never evaluated at runtime. Core refusals (`StateError`) reach
the client as tool errors carrying core's message; any other exception stays a crash the SDK
reports without its text.

A definition may name resolvers, parameter name to `Resolve`. The SDK runs them before the
handler, a resolver taking the whole request by the name `request`, and passes the handler each
outcome as a keyword argument of that name: the full `ElicitationResult`, so a declined round
reaches the handler to answer rather than aborting the call.
"""

import inspect
from dataclasses import dataclass, field
from time import perf_counter
from typing import TYPE_CHECKING, Any, Concatenate, Self

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.resolve import build_resolver_plans
from mcp.server.mcpserver.tools import Tool
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata
from mightymodels_core.primitives import StateError
from pydantic import BaseModel

from .call_log import CallRecord
from .dependencies import ServerDependencies
from .requests import REQUEST_ARGUMENT, RequestModel

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from mcp.server.mcpserver.resolve import Resolve
    from mcp.types import Icon, ToolAnnotations

    from .call_log import CallOutcome

type ToolContext = Context[ServerDependencies, Any]
type ToolHandler[R: RequestModel, V: BaseModel, **P = []] = Callable[
    Concatenate[R, ToolContext, P], Awaitable[V]
]

CONTEXT_ARGUMENT = 'ctx'
SLUG_ARGUMENT = 'slug'
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
class ToolDefinition[R: RequestModel, V: BaseModel, **P = []]:
    name: str
    title: str | None
    annotations: ToolAnnotations | None
    icon: Icon | None
    request_model: type[R]
    result_model: type[V]
    handler: ToolHandler[R, V, P]
    resolvers: Mapping[str, Resolve] = field(default_factory=dict)

    @property
    def description(self) -> str:
        return inspect.getdoc(self.handler) or ''

    @property
    def icons(self) -> list[Icon] | None:
        return None if self.icon is None else [self.icon]

    @property
    def resolved_params(self) -> dict[str, tuple[Resolve, bool]]:
        return {name: (resolver, True) for name, resolver in self.resolvers.items()}


@dataclass(slots=True, kw_only=True, frozen=True)
class ToolDefinitionPolicy[R: RequestModel, V: BaseModel, **P]:
    definition: ToolDefinition[R, V, P]

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
class RefusalTranslatingHandler[R: RequestModel, V: BaseModel, **P]:
    name: str
    handler: ToolHandler[R, V, P]

    def record_call(self, request: R, outcome: CallOutcome, started: float) -> None:
        CallRecord(
            tool_name=self.name,
            slug=getattr(request, SLUG_ARGUMENT, None),
            outcome=outcome,
            duration_ms=(perf_counter() - started) * 1000,
        ).emit()

    async def run(self, request: R, ctx: ToolContext, *args: P.args, **kwargs: P.kwargs) -> V:
        started = perf_counter()
        try:
            result = await self.handler(request, ctx, *args, **kwargs)
        except StateError as refusal:
            self.record_call(request, 'refused', started)
            raise ToolError(str(refusal)) from refusal
        except Exception:
            self.record_call(request, 'error', started)
            raise

        self.record_call(request, 'ok', started)
        return result


def create_tool[R: RequestModel, V: BaseModel, **P](definition: ToolDefinition[R, V, P]) -> Tool:
    request_model = definition.request_model
    translator = RefusalTranslatingHandler(name=definition.name, handler=definition.handler)
    resolved_params = definition.resolved_params
    return Tool(
        fn=translator.run,
        name=definition.name,
        title=definition.title,
        description=definition.description,
        parameters=request_model.model_json_schema(by_alias=True),
        fn_metadata=FuncMetadata(arg_model=request_model, output_model=definition.result_model),
        is_async=True,
        context_kwarg=CONTEXT_ARGUMENT,
        resolved_params=resolved_params,
        resolver_plans=build_resolver_plans(resolved_params, {REQUEST_ARGUMENT}),
        annotations=definition.annotations,
        icons=definition.icons,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ToolCatalog:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register[R: RequestModel, V: BaseModel, **P](
        self, definition: ToolDefinition[R, V, P]
    ) -> Self:
        if problem := ToolDefinitionPolicy(definition=definition).get_definition_problem():
            raise problem

        if definition.name in self.tools:
            raise DuplicateToolNameError(name=definition.name)

        self.tools[definition.name] = create_tool(definition)
        return self

    def list_tools(self) -> list[Tool]:
        return list(self.tools.values())
