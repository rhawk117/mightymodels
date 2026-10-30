"""Register tools that take one request model and the context, with complete metadata.

The tool is built from the definition's models rather than from the handler's signature, so
the handler's annotations are never evaluated at runtime. Core refusals (`StateError`) and the
operational database failures (a schema version mismatch, a busy, in-use or read-only database)
reach the client as tool errors carrying core's message; any other exception stays a crash the SDK
reports without its text. One `RefusalTranslator` does that and records the call for a handler and
for every resolver, so a refusal from either is logged as `refused`.

A definition may name resolvers, parameter name to `Resolve`. The SDK runs them before the
handler, a resolver taking the whole request by the name `request`, and passes the handler each
outcome as a keyword argument of that name: the full `ElicitationResult`, so a declined round
reaches the handler to answer rather than aborting the call.
"""

import inspect
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from time import perf_counter
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Concatenate,
    Protocol,
    Self,
    get_args,
    get_origin,
    get_type_hints,
    runtime_checkable,
)

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.resolve import Resolve, build_resolver_plans
from mcp.server.mcpserver.tools import Tool
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata
from mightymodels_core.database.errors import (
    BusyError,
    DatabaseInUseError,
    ReadOnlyDatabaseError,
    SchemaVersionError,
)
from mightymodels_core.primitives import StateError
from pydantic import BaseModel

from .call_log import CallRecord
from .dependencies import ServerDependencies
from .icons import load_icon
from .published_schema import inline_refs
from .requests import REQUEST_ARGUMENT, RequestModel

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator, Mapping
    from contextlib import AbstractAsyncContextManager

    from mcp.types import Icon, ToolAnnotations
    from mightymodels_core.edge import OpenState

    from .call_log import CallOutcome
    from .icons import IconName

type ToolContext = Context[ServerDependencies, Any]
type ToolHandler[R: RequestModel, V: BaseModel, **P = []] = Callable[
    Concatenate[R, ToolContext, P], Awaitable[V]
]


def open_tool_state(ctx: ToolContext) -> AbstractAsyncContextManager[OpenState]:
    return ctx.request_context.lifespan_context.state.open()


CONTEXT_ARGUMENT = 'ctx'
SLUG_ARGUMENT = 'slug'
REFUSALS = (StateError, SchemaVersionError, BusyError, DatabaseInUseError, ReadOnlyDatabaseError)
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
        title = self.definition.title
        return bool(title and title.strip())

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
class RefusalTranslator:
    name: str

    def record_call(self, request: object | None, outcome: CallOutcome, started: float) -> None:
        CallRecord(
            tool_name=self.name,
            slug=getattr(request, SLUG_ARGUMENT, None),
            outcome=outcome,
            duration_ms=(perf_counter() - started) * 1000,
        ).emit()

    @contextmanager
    def guard(self, request: object | None, started: float) -> Generator[None]:
        try:
            yield
        except REFUSALS as refusal:
            self.record_call(request, 'refused', started)
            raise ToolError(str(refusal)) from refusal
        except Exception:
            self.record_call(request, 'error', started)
            raise


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusalTranslatingHandler[R: RequestModel, V: BaseModel, **P]:
    translator: RefusalTranslator
    handler: ToolHandler[R, V, P]

    async def run(self, request: R, ctx: ToolContext, *args: P.args, **kwargs: P.kwargs) -> V:
        started = perf_counter()
        with self.translator.guard(request, started):
            result = await self.handler(request, ctx, *args, **kwargs)

        self.translator.record_call(request, 'ok', started)
        return result


def create_guarded_resolver(
    translator: RefusalTranslator, resolver: Callable[..., Any]
) -> Callable[..., Any]:
    if inspect.iscoroutinefunction(resolver):

        @wraps(resolver)
        async def guarded(**kwargs: Any) -> Any:
            with translator.guard(kwargs.get(REQUEST_ARGUMENT), perf_counter()):
                return await resolver(**kwargs)

        return guarded

    @wraps(resolver)
    def guarded_sync(**kwargs: Any) -> Any:
        with translator.guard(kwargs.get(REQUEST_ARGUMENT), perf_counter()):
            return resolver(**kwargs)

    return guarded_sync


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusalTranslatingResolvers:
    translator: RefusalTranslator
    guarded: dict[int, Callable[..., Any]] = field(default_factory=dict)

    def wrap_marker(self, marker: Resolve) -> Resolve:
        return Resolve(self.wrap(marker.fn))

    def wrap_hint(self, hint: Any) -> Any:
        if get_origin(hint) is not Annotated:
            return hint

        type_arg, *metadata = get_args(hint)
        wrapped = [self.wrap_marker(m) if isinstance(m, Resolve) else m for m in metadata]
        return Annotated[type_arg, *wrapped]

    def wrap(self, resolver: Callable[..., Any]) -> Callable[..., Any]:
        if known := self.guarded.get(id(resolver)):
            return known

        guarded = create_guarded_resolver(self.translator, resolver)
        self.guarded[id(resolver)] = guarded
        hints = get_type_hints(resolver, include_extras=True)
        guarded.__annotations__ = {name: self.wrap_hint(hint) for name, hint in hints.items()}
        return guarded


def create_tool[R: RequestModel, V: BaseModel, **P](definition: ToolDefinition[R, V, P]) -> Tool:
    request_model = definition.request_model
    translator = RefusalTranslator(name=definition.name)
    handler = RefusalTranslatingHandler(translator=translator, handler=definition.handler)
    resolvers = RefusalTranslatingResolvers(translator=translator)
    resolved_params = {
        name: (resolvers.wrap_marker(marker), wants_union)
        for name, (marker, wants_union) in definition.resolved_params.items()
    }
    return Tool(
        fn=handler.run,
        name=definition.name,
        title=definition.title,
        description=definition.description,
        parameters=inline_refs(request_model.model_json_schema(by_alias=True)),
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


@runtime_checkable
class ToolRegistrar(Protocol):
    def register_in(self, catalog: ToolCatalog) -> ToolCatalog: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class ToolSpec[R: RequestModel, V: BaseModel, **P = []]:
    name: str
    title: str
    annotations: ToolAnnotations
    icon: IconName
    request_model: type[R]
    result_model: type[V]
    handler: ToolHandler[R, V, P]
    resolvers: Mapping[str, Resolve] = field(default_factory=dict)

    def define(self) -> ToolDefinition[R, V, P]:
        return ToolDefinition(
            name=self.name,
            title=self.title,
            annotations=self.annotations,
            icon=load_icon(self.icon),
            request_model=self.request_model,
            result_model=self.result_model,
            handler=self.handler,
            resolvers=self.resolvers,
        )

    def register_in(self, catalog: ToolCatalog) -> ToolCatalog:
        return catalog.register(self.define())


def register_specs(catalog: ToolCatalog, specs: tuple[ToolRegistrar, ...]) -> ToolCatalog:
    for spec in specs:
        spec.register_in(catalog)

    return catalog
