from dataclasses import dataclass

import msgspec
from hypothesis import given
from hypothesis import strategies as st
from mightymodels_core.schemas.contract import (
    ApproveContractCommandParams,
    ContractCommandRow,
    ReceiptRow,
    RecordReceiptParams,
)
from mightymodels_core.schemas.crashouts import CrashoutRow, JournalCrashoutParams
from mightymodels_core.schemas.investigations import (
    AddInvestigationParams,
    AppendLedgerEntryParams,
    InvestigationRow,
    LedgerEntryRow,
)
from mightymodels_core.schemas.reviews import (
    RecordReviewRunParams,
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
    UpsertReviewDispositionParams,
    UpsertReviewFindingParams,
    UpsertReviewOutcomeParams,
)
from mightymodels_core.schemas.tasks import (
    AddTaskTransitionParams,
    TaskRow,
    TransitionRow,
    UpsertTaskParams,
)
from mightymodels_core.schemas.tickets import (
    ClosingRow,
    StageTicketParams,
    TicketRow,
    UpsertClosingParams,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class MirroredPair:
    name: str
    params: type[msgspec.Struct]
    row: type[msgspec.Struct]
    params_only: frozenset[str] = frozenset()
    row_only: frozenset[str] = frozenset()


MIRRORED_PAIRS = (
    MirroredPair(
        name='crashout',
        params=JournalCrashoutParams,
        row=CrashoutRow,
        params_only=frozenset({'repository_id'}),
        row_only=frozenset({'id'}),
    ),
    MirroredPair(name='closing', params=UpsertClosingParams, row=ClosingRow),
    MirroredPair(
        name='ticket',
        params=StageTicketParams,
        row=TicketRow,
        params_only=frozenset({'repository_id'}),
        row_only=frozenset({'id', 'status', 'investigations'}),
    ),
    MirroredPair(
        name='contract-command',
        params=ApproveContractCommandParams,
        row=ContractCommandRow,
        params_only=frozenset({'ticket_id'}),
        row_only=frozenset({'id'}),
    ),
    MirroredPair(
        name='receipt',
        params=RecordReceiptParams,
        row=ReceiptRow,
        params_only=frozenset({'contract_command_id'}),
        row_only=frozenset({'command_key'}),
    ),
    MirroredPair(
        name='review-run',
        params=RecordReviewRunParams,
        row=ReviewRunRow,
        params_only=frozenset({'repository_id'}),
        row_only=frozenset({'id'}),
    ),
    MirroredPair(
        name='review-finding',
        params=UpsertReviewFindingParams,
        row=ReviewFindingRow,
        params_only=frozenset({'review_run_id'}),
        row_only=frozenset({'id'}),
    ),
    MirroredPair(
        name='ledger-entry',
        params=AppendLedgerEntryParams,
        row=LedgerEntryRow,
        params_only=frozenset({'investigation_id'}),
    ),
    MirroredPair(
        name='task',
        params=UpsertTaskParams,
        row=TaskRow,
        params_only=frozenset({'ticket_id'}),
        row_only=frozenset({'id'}),
    ),
    MirroredPair(
        name='task-transition',
        params=AddTaskTransitionParams,
        row=TransitionRow,
        params_only=frozenset({'task_id'}),
        row_only=frozenset({'task_key'}),
    ),
    MirroredPair(
        name='review-disposition',
        params=UpsertReviewDispositionParams,
        row=ReviewDispositionRow,
        params_only=frozenset({'review_finding_id'}),
        row_only=frozenset({'id', 'finding_key'}),
    ),
    MirroredPair(
        name='review-outcome',
        params=UpsertReviewOutcomeParams,
        row=ReviewOutcomeRow,
        params_only=frozenset({'review_disposition_id'}),
        row_only=frozenset({'finding_key'}),
    ),
    MirroredPair(
        name='investigation',
        params=AddInvestigationParams,
        row=InvestigationRow,
        params_only=frozenset({'repository_id'}),
        row_only=frozenset({'id', 'created_at'}),
    ),
)


def field_types(struct: type[msgspec.Struct]) -> dict[str, object]:
    return {field.name: field.type for field in msgspec.structs.fields(struct)}


class TestMirroredFields:
    pairs = st.sampled_from(MIRRORED_PAIRS)

    @given(pair=pairs)
    def test_shared_fields_match_by_name_and_type(self, pair: MirroredPair) -> None:
        params_fields = field_types(pair.params)
        row_fields = field_types(pair.row)
        assert pair.params_only <= params_fields.keys()
        assert pair.row_only <= row_fields.keys()
        shared_params = {k: v for k, v in params_fields.items() if k not in pair.params_only}
        shared_row = {k: v for k, v in row_fields.items() if k not in pair.row_only}
        assert shared_params == shared_row
