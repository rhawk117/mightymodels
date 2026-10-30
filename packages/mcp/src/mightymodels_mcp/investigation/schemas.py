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
    kind: EntryKind = Field(description='What sort of entry this is.')
    text: ProseText = Field(description='The entry itself, stated in one claim.')
    source: EntrySource = Field(description='Where the entry came from.')
    cite: CiteText | None = Field(
        default=None,
        description='The file:line or URL the entry rests on; some sources require it.',
    )
    supersedes: tuple[int, ...] = Field(
        default=(), description='The sequence numbers of earlier entries this one retires.'
    )


class InvestigationStartRequest(RequestModel):
    target: ProseText = Field(description='What is being investigated, in a sentence.')
    kind: TargetKind | None = Field(
        default=None, description='What kind of target it is; omit it and the user is asked.'
    )


class InvestigationAddRequest(RequestModel):
    investigation_id: SlugField
    round: int = Field(description='The investigation round these entries belong to.')
    entries: tuple[LedgerEntry, ...] = Field(description='The entries to append to the ledger.')


class InvestigationRenderRequest(RequestModel):
    investigation_id: SlugField


class InvestigationKnownsRequest(RequestModel):
    investigation_id: SlugField
    kinds: tuple[EntryKind, ...] = Field(
        default=SECTION_KINDS,
        min_length=1,
        description='The entry kinds to list; omit it to list every section kind.',
    )
    limit: int = Field(
        default=KNOWNS_LIMIT, ge=1, description='The most live entries listed for each kind.'
    )


class InvestigationListRequest(RequestModel):
    pass
