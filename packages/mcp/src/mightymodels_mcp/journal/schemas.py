"""The journal tools' requests.

The vocabulary is core's. A blank field and an empty list of failures are refused by core's
crashout policy, so the requests hold only the shapes and the length limits.
"""

from mightymodels_core.vocabulary.crashouts import CrashoutSeverity, Verdict
from mightymodels_core.vocabulary.similarity import SimilarityKind
from pydantic import Field

from mightymodels_mcp.server.requests import NameText, ProseText, RequestModel, SlugField


class CrashoutAddRequest(RequestModel):
    ticket: SlugField | None = Field(
        default=None, description='The ticket the crashout happened on, if any.'
    )
    branch: NameText | None = Field(
        default=None, description='The branch the crashout happened on, if any.'
    )
    severity: CrashoutSeverity = Field(description='How severe the crashout was.')
    verdict: Verdict = Field(
        description='Whether the crashout was deserved, split or unreasonable.'
    )
    rant: ProseText = Field(description='The crashout, told in your own words.')
    failures: tuple[ProseText, ...] = Field(description='What went wrong, one failure per entry.')
    root_cause: ProseText = Field(description='Why the failures happened.')
    corrective_action: ProseText = Field(
        description='What was or will be done to prevent a repeat.'
    )
    barked_back: bool = Field(
        description='Whether the reporter barked back at the one who caused it.'
    )


class CrashoutStatsRequest(RequestModel):
    pass


class CrashoutLastRequest(RequestModel):
    pass


class SimilaritySearchRequest(RequestModel):
    query: ProseText = Field(description='The text to find similar journal entries for.')
    kind: SimilarityKind | None = Field(
        default=None, description='Search only this kind of entry; omit it to search every kind.'
    )
