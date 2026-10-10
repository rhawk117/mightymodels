"""The `similarity` tool: a handler checks the call's arguments and asks the similarity service.

`search` needs the text to look for, and `search_similar` is the one place that refuses a call
without it. The kind narrows the search to one kind of row.

`ResolvedSimilarity` is a plain assignment because the SDK does not see a `Resolve` marker behind
a PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.tools.protocol import (
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels_plugin.tools.request import ProseText
from mightymodels_plugin.tools.similarity.schema import (
    SimilarityAction,
    SimilarityKind,
    SimilarityView,
)
from mightymodels_plugin.tools.similarity.service import SimilarityService


@dataclass(slots=True, kw_only=True, frozen=True)
class SimilarityCall:
    query: str | None
    kind: SimilarityKind | None


def search_similar(similarity: SimilarityService, call: SimilarityCall) -> SimilarityView:
    if call.query is None:
        raise MissingArgumentsError(SimilarityAction.SEARCH, 'a query holding the text to look for')
    return similarity.search(call.query, call.kind)


def lifespan_similarity(ctx: Context[ServedState]) -> SimilarityService:
    return served_services(ctx).similarity


ResolvedSimilarity = Annotated[SimilarityService, Resolve(lifespan_similarity)]


@dataclass(slots=True, kw_only=True, frozen=True)
class SimilarityTool:
    handlers: Mapping[
        SimilarityAction, ServiceHandler[SimilarityService, SimilarityCall, SimilarityView]
    ]

    def similarity(
        self,
        action: SimilarityAction,
        query: ProseText | None = None,
        kind: SimilarityKind | None = None,
        *,
        similar: ResolvedSimilarity,
    ) -> SimilarityView:
        """Search the stored ledger entries, scout reports, review findings and crashouts."""
        call = SimilarityCall(query=query, kind=kind)
        return dispatch_to_service(self.handlers, action, call, service=similar)


similarity_tool = SimilarityTool(
    handlers=MappingProxyType({SimilarityAction.SEARCH: search_similar})
)
similarity_action_tool: ActionTool[
    SimilarityAction, SimilarityService, SimilarityCall, SimilarityView
] = similarity_tool
