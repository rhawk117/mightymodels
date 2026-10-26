"""The investigation tools' requests.

The vocabulary is core's. Whether an entry has the cite its source needs, a source it may use, a
text, and a round and supersedes that fit the ledger stay core's rules, so the requests hold only
the shapes. An entry of kind `target` is refused here, because core's kinds do not have one.
"""

from typing import Annotated

from mightymodels_core.investigations.ledger import KNOWNS_LIMIT, SECTION_KINDS
from mightymodels_core.investigations.records import TargetKind
from mightymodels_core.vocabulary.investigations import EntryKind, EntrySource
from pydantic import Field, StringConstraints

from mightymodels_mcp.server.requests import PROSE_LIMIT, ProseText, RequestModel, SlugField

type CiteText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PROSE_LIMIT)
]


class LedgerEntry(RequestModel):
    kind: EntryKind
    text: ProseText
    source: EntrySource
    cite: CiteText | None = None
    supersedes: tuple[int, ...] = ()


class InvestigationStartRequest(RequestModel):
    target: ProseText
    kind: TargetKind | None = None


class InvestigationAddRequest(RequestModel):
    investigation_id: SlugField
    round: int
    entries: tuple[LedgerEntry, ...]


class InvestigationRenderRequest(RequestModel):
    investigation_id: SlugField


class InvestigationKnownsRequest(RequestModel):
    investigation_id: SlugField
    kinds: Annotated[tuple[EntryKind, ...], Field(min_length=1)] = SECTION_KINDS
    limit: Annotated[int, Field(ge=1)] = KNOWNS_LIMIT


class InvestigationListRequest(RequestModel):
    pass
