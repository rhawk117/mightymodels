"""The journal tools' requests.

The vocabulary is core's. A blank field and an empty list of failures are refused by core's
crashout policy, so the requests hold only the shapes and the length limits.
"""

from mightymodels_core.vocabulary.crashouts import CrashoutSeverity, Verdict
from mightymodels_core.vocabulary.similarity import SimilarityKind

from mightymodels_mcp.server.requests import NameText, ProseText, RequestModel, SlugField


class CrashoutAddRequest(RequestModel):
    ticket: SlugField | None = None
    branch: NameText | None = None
    severity: CrashoutSeverity
    verdict: Verdict
    rant: ProseText
    failures: tuple[ProseText, ...]
    root_cause: ProseText
    corrective_action: ProseText
    barked_back: bool


class CrashoutStatsRequest(RequestModel):
    pass


class CrashoutLastRequest(RequestModel):
    pass


class SimilaritySearchRequest(RequestModel):
    query: ProseText
    kind: SimilarityKind | None = None
