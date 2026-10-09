"""Text a caller writes is held to the length of the column it is stored in.

Every string field of every request model is listed here once, beside the column that stores it or
the ceiling it is held to when no column of its own does, so a field a request model gains fails
the listing until it is given a maximum.

A finding id is the one text a request model does not hold to its column. It carries its pattern
and the ceiling, and it is stored only when it names a finding the run holds, so a longer one is
refused as unknown and nothing is written.
"""

from collections.abc import Callable, Collection, Generator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeAliasType, get_args

import pytest
from mightymodels_plugin.clock import now
from mightymodels_plugin.database import Database
from mightymodels_plugin.declarative import NAME_LIMIT, PROSE_LIMIT, Base
from mightymodels_plugin.routing import Depth
from mightymodels_plugin.run_id import RunId
from mightymodels_plugin.slug import SLUG_LIMIT, Slug
from mightymodels_plugin.tools.close.schema import Closing
from mightymodels_plugin.tools.close.tables import ClosingRow
from mightymodels_plugin.tools.contract.repository import contract_transaction
from mightymodels_plugin.tools.contract.schema import ContractCommand
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.contract.tables import CommandRow
from mightymodels_plugin.tools.crashout.schema import CrashoutEntry
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.crashout.tables import CrashoutRow
from mightymodels_plugin.tools.investigation.schema import InvestigationStart, LedgerEntry
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow
from mightymodels_plugin.tools.request import RequestModel
from mightymodels_plugin.tools.review.errors import UnknownFindingError
from mightymodels_plugin.tools.review.repository import DecidedFinding, review_transaction
from mightymodels_plugin.tools.review.schema import (
    Decision,
    DisposePayload,
    Disposition,
    Emphasis,
    Evidence,
    EvidenceKind,
    Finding,
    FindingInput,
    Kind,
    Persona,
    ResolvePayload,
    ReviewRun,
    ReviewScope,
    Severity,
    Shape,
    StartPayload,
)
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.review.tables import (
    FINDING_ID_LIMIT,
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
)
from mightymodels_plugin.tools.task.schema import TaskMark, TaskPayload, TaskStart, TaskVerification
from mightymodels_plugin.tools.task.tables import TaskRow
from mightymodels_plugin.tools.tests.support import (
    ActivityKind,
    DatabaseActivity,
    StateServer,
    table_of,
    text_of,
)
from mightymodels_plugin.tools.ticket.schema import TicketAnswers, TicketContext
from mightymodels_plugin.tools.ticket.tables import TicketRow
from pydantic import ValidationError
from sqlalchemy import String

type Placed = Callable[[str], object]
type Spelled = Callable[[int], str]
type StringSchema = Collection[object]

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
RUN = RunId('20260928-120000')
TOO_LONG = 'string_too_long'
OFF_THE_PATTERN = 'string_pattern_mismatch'
STARTED = ReviewRun(
    run_id=RUN,
    slug=None,
    scope=ReviewScope.CODEBASE,
    base=None,
    head=None,
    depth=Depth.DEEP,
    emphasis=Emphasis.BALANCED,
    weights=dict.fromkeys(Persona, 0.5),
    personas=tuple(Persona),
    models={},
    created_at='2026-09-28T12:00:00+00:00',
)
FINDING = Finding(
    id='F1',
    sources=('MV-1',),
    severity=Severity.HIGH,
    kind=Kind.DEFECT,
    security=False,
    title='the drain loop sleeps between batches',
    location='src/queue.py:12',
    fix='drain in one pass',
    verify='run the drain test',
)
VALID: Mapping[type[RequestModel], dict[str, object]] = MappingProxyType(
    {
        Closing: {'shipped': 'the drain runs in one pass'},
        ContractCommand: {'id': 'T1.AC-1', 'argv': ['true'], 'approved_by': 'user'},
        CrashoutEntry: {
            'severity': 'heated',
            'verdict': 'deserved',
            'rant': 'why did you skip the tests',
            'failures': ['skipped the tests'],
            'root_cause': 'optimised for speed',
            'corrective_action': 'run the gate before reporting',
            'barked_back': False,
        },
        LedgerEntry: {'kind': 'open', 'text': 'why is the drain slow', 'source': 'user'},
        InvestigationStart: {'target': 'the drain loop', 'kind': 'behavior'},
        Evidence: {'kind': 'metric', 'cite': 'cyclomatic complexity 14'},
        FindingInput: {
            'sources': ['MV-1'],
            'severity': 'High',
            'title': 'the drain loop sleeps between batches',
            'location': 'src/queue.py:12',
            'fix': 'drain in one pass',
            'verify': 'run the drain test',
        },
        StartPayload: {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'},
        Disposition: {'decision': 'fix'},
        DisposePayload: {'by': 'user', 'decisions': {'F1': {'decision': 'fix'}}},
        ResolvePayload: {'finding': 'F1', 'result': 'fixed'},
        TaskStart: {'by': 'engineer', 'owned': ['src/queue.py']},
        TaskVerification: {'commit': 'abc1234'},
        TaskMark: {'to': 'failed', 'reason': 'the drain test fails'},
        TaskPayload: {},
        TicketAnswers: {
            'summary': 'Retry queue drains slowly',
            'scope': 'large',
            'compaction': True,
            'branch': 'fix/retry-queue',
            'context': ['drain loop sleeps between batches'],
        },
        TicketContext: {'context': ['drain loop sleeps between batches']},
    }
)


def length_of(row_type: type[Base], column: str) -> int:
    declared = table_of(row_type).columns[column].type
    assert isinstance(declared, String)
    assert declared.length is not None
    return declared.length


def alone(text: str) -> object:
    return text


def in_a_list(text: str) -> object:
    return [text]


def naming_a_decision(text: str) -> object:
    return {text: {'decision': 'fix'}}


def naming_an_assertion(text: str) -> object:
    return {text: 'the drain test passes'}


def as_an_assertion(text: str) -> object:
    return {'T1.AC-1': text}


def plain(length: int) -> str:
    return 'x' * length


def finding_id(length: int) -> str:
    return 'F' + '1' * (length - 1)


def source_id(length: int) -> str:
    return 'MV-' + '1' * (length - 3)


def task_id(length: int) -> str:
    return 'T' + '1' * (length - 1)


@dataclass(slots=True, kw_only=True, frozen=True)
class CallerText:
    model: type[RequestModel]
    field: str
    limit: int
    part: str = 'whole'
    placed: Placed = alone
    spelled: Spelled = plain
    refused_as: str = TOO_LONG

    def refusals(self, length: int) -> list[str]:
        request = VALID[self.model] | {self.field: self.placed(self.spelled(length))}
        try:
            self.model.model_validate(request)
        except ValidationError as refused:
            return [error['type'] for error in refused.errors()]
        return []


def stored(model: type[RequestModel], field: str, row_type: type[Base], column: str) -> CallerText:
    return CallerText(model=model, field=field, limit=length_of(row_type, column))


def carries_text(annotation: object) -> bool:
    if isinstance(annotation, TypeAliasType):
        return carries_text(annotation.__value__)
    return annotation is str or any(map(carries_text, get_args(annotation)))


def strings_in(node: object) -> Generator[StringSchema]:
    if isinstance(node, dict):
        if node.get('type') == 'string':
            yield node
        yield from strings_in(list(node.values()))
    if isinstance(node, list):
        for child in node:
            yield from strings_in(child)


def text_fields() -> set[tuple[str, str]]:
    return {
        (model.__name__, name)
        for model in RequestModel.__subclasses__()
        for name, field in model.model_fields.items()
        if carries_text(field.annotation)
    }


class TestEveryStringOfARequestModel:
    IN_A_COLUMN = (
        stored(Closing, 'shipped', ClosingRow, 'shipped'),
        stored(Closing, 'pr', ClosingRow, 'pr'),
        stored(ContractCommand, 'id', CommandRow, 'command_id'),
        stored(ContractCommand, 'approved_by', CommandRow, 'approved_by'),
        stored(CrashoutEntry, 'branch', CrashoutRow, 'branch'),
        stored(CrashoutEntry, 'rant', CrashoutRow, 'rant'),
        stored(CrashoutEntry, 'root_cause', CrashoutRow, 'root_cause'),
        stored(CrashoutEntry, 'corrective_action', CrashoutRow, 'corrective_action'),
        stored(LedgerEntry, 'text', LedgerEntryRow, 'text'),
        stored(LedgerEntry, 'cite', LedgerEntryRow, 'cite'),
        stored(InvestigationStart, 'target', LedgerEntryRow, 'text'),
        stored(Evidence, 'cite', ReviewFindingRow, 'evidence_cite'),
        stored(FindingInput, 'title', ReviewFindingRow, 'title'),
        stored(FindingInput, 'location', ReviewFindingRow, 'location'),
        stored(FindingInput, 'fix', ReviewFindingRow, 'fix'),
        stored(FindingInput, 'verify', ReviewFindingRow, 'verify'),
        stored(StartPayload, 'base', ReviewRunRow, 'base'),
        stored(Disposition, 'reason', ReviewDispositionRow, 'reason'),
        stored(DisposePayload, 'by', ReviewDispositionRow, 'by'),
        stored(ResolvePayload, 'commit', ReviewOutcomeRow, 'commit'),
        stored(ResolvePayload, 'reason', ReviewOutcomeRow, 'reason'),
        stored(TaskVerification, 'commit', TaskRow, 'commit'),
        stored(TicketAnswers, 'summary', TicketRow, 'summary'),
        stored(TicketAnswers, 'branch', TicketRow, 'branch'),
        stored(TicketAnswers, 'jira', TicketRow, 'jira'),
        CallerText(
            model=TaskPayload,
            field='task_id',
            limit=length_of(TaskRow, 'task_id'),
            spelled=task_id,
            refused_as=OFF_THE_PATTERN,
        ),
    )
    IN_NO_COLUMN_OF_ITS_OWN = (
        CallerText(
            model=Closing, field='gotchas', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
        CallerText(
            model=ContractCommand, field='argv', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
        CallerText(
            model=CrashoutEntry, field='failures', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
        CallerText(
            model=FindingInput,
            field='sources',
            limit=PROSE_LIMIT,
            part='item',
            placed=in_a_list,
            spelled=source_id,
        ),
        CallerText(
            model=DisposePayload,
            field='decisions',
            limit=PROSE_LIMIT,
            part='key',
            placed=naming_a_decision,
            spelled=finding_id,
        ),
        CallerText(model=ResolvePayload, field='finding', limit=PROSE_LIMIT, spelled=finding_id),
        CallerText(
            model=TaskStart, field='owned', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
        CallerText(
            model=TaskVerification,
            field='assertions',
            limit=PROSE_LIMIT,
            part='key',
            placed=naming_an_assertion,
        ),
        CallerText(
            model=TaskVerification,
            field='assertions',
            limit=PROSE_LIMIT,
            part='value',
            placed=as_an_assertion,
        ),
        CallerText(model=TaskMark, field='reason', limit=PROSE_LIMIT),
        CallerText(
            model=TicketAnswers, field='context', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
        CallerText(
            model=TicketAnswers,
            field='reference_urls',
            limit=PROSE_LIMIT,
            part='item',
            placed=in_a_list,
        ),
        CallerText(
            model=TicketAnswers,
            field='investigations',
            limit=SLUG_LIMIT,
            part='item',
            placed=in_a_list,
        ),
        CallerText(
            model=TicketContext, field='context', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
    )
    TEXTS = (*IN_A_COLUMN, *IN_NO_COLUMN_OF_ITS_OWN)
    EACH_TEXT = tuple(
        pytest.param(text, id=f'{text.model.__name__}.{text.field}-{text.part}') for text in TEXTS
    )

    def test_is_listed_here_with_its_maximum(self) -> None:
        assert {(text.model.__name__, text.field) for text in self.TEXTS} == text_fields()

    @pytest.mark.parametrize('text', EACH_TEXT)
    def test_is_accepted_at_its_maximum(self, text: CallerText) -> None:
        assert text.refusals(text.limit) == []

    @pytest.mark.parametrize('text', EACH_TEXT)
    def test_is_refused_one_character_past_its_maximum(self, text: CallerText) -> None:
        assert text.refused_as in text.refusals(text.limit + 1)


class TestEveryFreeStringAToolAccepts:
    BOUND_OTHERWISE = frozenset({'enum', 'const', 'pattern'})

    @pytest.fixture
    def free_strings(self, state_server: StateServer) -> list[StringSchema]:
        published = [tool.input_schema for tool in state_server.tools().values()]
        return [
            string
            for string in strings_in(published)
            if not self.BOUND_OTHERWISE.intersection(string)
        ]

    def test_states_its_maximum_in_the_schema_its_tool_publishes(
        self, free_strings: list[StringSchema]
    ) -> None:
        assert free_strings != []
        assert [string for string in free_strings if 'maxLength' not in string] == []


class TestATextOneCharacterTooLong:
    ENTRY = MappingProxyType(VALID[CrashoutEntry])
    CALLS = (
        pytest.param(
            'close',
            {'action': 'close', 'slug': SLUG, 'closing': {'shipped': plain(PROSE_LIMIT + 1)}},
            PROSE_LIMIT,
            id='close',
        ),
        pytest.param(
            'contract',
            {
                'action': 'approve',
                'slug': SLUG,
                'commands': [{**VALID[ContractCommand], 'approved_by': plain(NAME_LIMIT + 1)}],
            },
            NAME_LIMIT,
            id='contract',
        ),
        pytest.param(
            'crashout',
            {'action': 'add', 'entry': {**ENTRY, 'rant': plain(PROSE_LIMIT + 1)}},
            PROSE_LIMIT,
            id='crashout',
        ),
        pytest.param(
            'investigation',
            {
                'action': 'start',
                'payload': {'request': {'target': plain(PROSE_LIMIT + 1), 'kind': 'behavior'}},
            },
            PROSE_LIMIT,
            id='investigation',
        ),
        pytest.param(
            'review',
            {'action': 'start', 'payload': {**VALID[StartPayload], 'base': plain(NAME_LIMIT + 1)}},
            NAME_LIMIT,
            id='review',
        ),
        pytest.param(
            'task',
            {
                'action': 'start',
                'slug': SLUG,
                'payload': {
                    'task_id': 'T1',
                    'change': {'by': 'engineer', 'owned': [plain(PROSE_LIMIT + 1)]},
                },
            },
            PROSE_LIMIT,
            id='task',
        ),
        pytest.param(
            'ticket',
            {
                'action': 'write',
                'slug': SLUG,
                'fields': {**VALID[TicketAnswers], 'branch': plain(NAME_LIMIT + 1)},
            },
            NAME_LIMIT,
            id='ticket',
        ),
    )

    @pytest.mark.parametrize(('name', 'arguments', 'limit'), CALLS)
    def test_is_refused_by_the_tool_before_any_row_is_written(
        self,
        name: str,
        arguments: dict[str, object],
        limit: int,
        connected_server: StateServer,
        tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
    ) -> None:
        (result,) = connected_server.call((name, arguments))

        assert result.is_error
        assert f'String should have at most {limit} characters' in text_of(result)
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert connected_server.files_on_disk() == tree_after_the_connect


class TestATextAtTheLengthOfItsColumn:
    RANT = plain(PROSE_LIMIT)
    COMMAND = plain(NAME_LIMIT)
    APPROVER = plain(NAME_LIMIT)

    @pytest.fixture
    def journaled_rant(self, crashout_service: CrashoutService) -> str | None:
        crashout_service.add(
            CrashoutEntry.model_validate(VALID[CrashoutEntry] | {'rant': self.RANT})
        )
        journaled = crashout_service.last().entry
        return None if journaled is None else journaled.rant

    @pytest.fixture
    def approved_command(
        self, contract_service: ContractService, repository_database: Database
    ) -> tuple[str, str]:
        command = ContractCommand(id=self.COMMAND, argv=('true',), approved_by=self.APPROVER)
        contract_service.approve(TICKET, [command])
        with contract_transaction(repository_database) as repository:
            (row,) = repository.commands(TICKET)
            return row.command_id, row.approved_by

    def test_is_stored_whole_in_a_prose_column(self, journaled_rant: str | None) -> None:
        assert journaled_rant == self.RANT

    def test_is_stored_whole_in_a_name_column(self, approved_command: tuple[str, str]) -> None:
        assert approved_command == (self.COMMAND, self.APPROVER)


class TestAFindingIdLongerThanItsColumn:
    UNSTORED = finding_id(FINDING_ID_LIMIT + 1)

    DECIDED = DisposePayload(by='user', decisions={UNSTORED: Disposition(decision='fix')})

    @pytest.fixture
    def decisions_stored_after_the_refusal(
        self, review_service: ReviewService, repository_database: Database
    ) -> int:
        with review_transaction(repository_database) as repository:
            repository.record_run(STARTED)
            repository.record_findings(RUN, [FINDING])
        with pytest.raises(UnknownFindingError):
            review_service.dispose(RUN, self.DECIDED)
        with review_transaction(repository_database) as repository:
            return len(repository.decisions.disposition_rows(RUN))

    def test_names_no_stored_finding_so_its_decision_is_refused_and_not_stored(
        self, decisions_stored_after_the_refusal: int
    ) -> None:
        assert decisions_stored_after_the_refusal == 0


class TestTextStoredLongerThanARequestMayCarry:
    CITE = plain(PROSE_LIMIT + 1)
    REASON = 'r' * (PROSE_LIMIT + 1)

    @pytest.fixture
    def report_of_a_run_holding_it(
        self, review_service: ReviewService, repository_database: Database
    ) -> str:
        evidence = Evidence.model_construct(kind=EvidenceKind.METRIC, cite=self.CITE)
        finding = FINDING.model_copy(update={'evidence': evidence})
        decided = DecidedFinding(
            finding_id=finding.id, decision=Decision.DEFER, reason=self.REASON, by='user', at=now()
        )
        with review_transaction(repository_database) as repository:
            repository.record_run(STARTED)
            repository.record_findings(RUN, [finding])
            repository.decisions.record_dispositions(RUN, [decided])
        return review_service.report(RUN, Shape.FULL).text

    def test_is_read_back_whole_and_leaves_its_run_readable(
        self, report_of_a_run_holding_it: str
    ) -> None:
        assert self.CITE in report_of_a_run_holding_it
        assert self.REASON in report_of_a_run_holding_it
