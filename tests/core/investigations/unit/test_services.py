"""The investigation service over the fakes: start, add, render, knowns and list rounds."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.investigations import (
    AddRequest,
    CiteRequiredError,
    KnownsSelection,
    RoundRegressionError,
    StartRequest,
    UnknownInvestigationError,
)
from mightymodels_core.primitives import RedactedTextTooLongError

from tests.core.investigations.conftest import (
    HEAD,
    MOMENT,
    STARTED,
    UNADDED,
    create_entry,
    create_incoming,
)

if TYPE_CHECKING:
    from mightymodels_core.investigations import IncomingEntry

    from tests.core.investigations.conftest import ServiceHarness


def create_start(target: str = 'Retry policy') -> StartRequest:
    return StartRequest(target=target, kind='behavior')


def create_add(*entries: IncomingEntry, round_number: int = 1) -> AddRequest:
    return AddRequest(round=round_number, entries=entries, head=HEAD)


class TestStart:
    def test_the_investigation_is_named_after_the_day_and_the_target(
        self, service_harness: ServiceHarness
    ) -> None:
        started = service_harness.service.start(create_start())
        assert started.investigation == STARTED

    def test_the_target_and_kind_are_stored(self, service_harness: ServiceHarness) -> None:
        service_harness.service.start(StartRequest(target='Retry policy', kind='claim'))
        stored = service_harness.investigations.investigation(STARTED)
        assert stored is not None
        assert (stored.target, stored.kind) == ('Retry policy', 'claim')

    def test_a_repeated_target_on_the_same_day_gets_a_counter(
        self, service_harness: ServiceHarness
    ) -> None:
        keys = [service_harness.service.start(create_start()).investigation for _ in range(3)]
        assert keys == [STARTED, f'{STARTED}-2', f'{STARTED}-3']

    def test_the_target_is_stored_redacted_and_named_without_the_secret(
        self, service_harness: ServiceHarness
    ) -> None:
        secret = 'ghp_' + 'a' * 36
        started = service_harness.service.start(create_start(f'leak {secret}'))
        stored = service_harness.investigations.investigation(started.investigation)
        assert stored is not None
        assert secret not in stored.target
        assert secret not in started.investigation

    def test_a_target_past_the_prose_limit_is_refused(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(RedactedTextTooLongError):
            service_harness.service.start(create_start('x' * 4001))
        assert service_harness.investigations.ledger.investigations == {}

    def test_the_target_goes_to_the_similarity_repository(
        self, service_harness: ServiceHarness
    ) -> None:
        service_harness.service.start(create_start())
        written = service_harness.similarity.entry('ledger-entry', f'{STARTED} target')
        assert written is not None
        assert written.text == 'Retry policy'

    def test_a_target_like_an_earlier_one_reports_the_duplicate(
        self, service_harness: ServiceHarness
    ) -> None:
        service_harness.service.start(create_start('retry policy for webhook delivery'))
        again = service_harness.service.start(create_start('webhook delivery retry policy'))
        assert len(again.duplicates) == 1


@pytest.fixture
def started_harness(service_harness: ServiceHarness) -> ServiceHarness:
    service_harness.service.start(create_start())
    return service_harness


def add_batch(harness: ServiceHarness, request: AddRequest) -> None:
    harness.service.add(STARTED, request)


class TestAdd:
    def test_entries_are_numbered_from_one_and_stamped(
        self, started_harness: ServiceHarness
    ) -> None:
        added = started_harness.service.add(
            STARTED, create_add(create_incoming(), create_incoming('open', cite=None))
        )
        stored = started_harness.investigations.entries(STARTED)
        assert added.seqs == (1, 2)
        assert {(record.round, record.at, record.head) for record in stored} == {(1, MOMENT, HEAD)}

    def test_numbering_continues_across_batches(self, started_harness: ServiceHarness) -> None:
        add_batch(started_harness, create_add(create_incoming()))
        added = started_harness.service.add(STARTED, create_add(create_incoming()))
        assert added.seqs == (2,)

    def test_an_entry_may_supersede_an_earlier_one(self, started_harness: ServiceHarness) -> None:
        add_batch(started_harness, create_add(create_incoming()))
        add_batch(started_harness, create_add(create_incoming(supersedes=(1,))))
        assert started_harness.investigations.entries(STARTED)[1].supersedes == (1,)


class TestAddRefusals:
    def test_an_unknown_investigation_is_refused(self, service_harness: ServiceHarness) -> None:
        with pytest.raises(UnknownInvestigationError):
            service_harness.service.add(UNADDED, create_add(create_incoming()))

    def test_a_round_before_the_latest_is_refused_and_stores_nothing(
        self, started_harness: ServiceHarness
    ) -> None:
        add_batch(started_harness, create_add(create_incoming(), round_number=2))
        with pytest.raises(RoundRegressionError):
            add_batch(started_harness, create_add(create_incoming(), round_number=1))
        assert len(started_harness.investigations.entries(STARTED)) == 1

    def test_one_refused_entry_refuses_the_batch(self, started_harness: ServiceHarness) -> None:
        batch = create_add(create_incoming(), create_incoming(cite=None))
        with pytest.raises(CiteRequiredError):
            add_batch(started_harness, batch)
        assert started_harness.investigations.entries(STARTED) == []


class TestAddWrites:
    def test_a_secret_is_redacted_and_counted(self, started_harness: ServiceHarness) -> None:
        secret = 'ghp_' + 'a' * 36
        added = started_harness.service.add(
            STARTED, create_add(create_incoming(text=f'token {secret}'))
        )
        [stored] = started_harness.investigations.entries(STARTED)
        assert secret not in stored.text
        assert added.redactions == 1

    def test_every_entry_goes_to_the_similarity_repository(
        self, started_harness: ServiceHarness
    ) -> None:
        add_batch(
            started_harness, create_add(create_incoming(text='first fact'), create_incoming())
        )
        written = started_harness.similarity.entry('ledger-entry', f'{STARTED} e1')
        assert written is not None
        assert written.text == 'first fact'
        assert started_harness.similarity.entry('ledger-entry', f'{STARTED} e2') is not None

    def test_an_entry_like_an_earlier_one_reports_the_duplicate_and_is_stored(
        self, started_harness: ServiceHarness
    ) -> None:
        wording = 'the webhook dispatcher retries failed deliveries with backoff'
        add_batch(started_harness, create_add(create_incoming(text=wording)))
        added = started_harness.service.add(STARTED, create_add(create_incoming(text=wording)))
        assert len(added.duplicates) == 1
        assert len(started_harness.investigations.entries(STARTED)) == 2


class TestRead:
    @pytest.fixture
    def filled_harness(self, service_harness: ServiceHarness) -> ServiceHarness:
        service_harness.service.start(create_start())
        service_harness.investigations.append(STARTED, [create_entry(1), create_entry(2)])
        return service_harness

    def test_render_returns_the_ledger(self, filled_harness: ServiceHarness) -> None:
        ledger = filled_harness.service.render(STARTED)
        assert (ledger.key, ledger.latest_round, len(ledger.records)) == (STARTED, 1, 2)

    def test_render_refuses_an_unknown_investigation(self, service_harness: ServiceHarness) -> None:
        with pytest.raises(UnknownInvestigationError):
            service_harness.service.render(UNADDED)

    def test_knowns_return_the_live_rows_at_the_head(self, filled_harness: ServiceHarness) -> None:
        knowns = filled_harness.service.knowns(STARTED, KnownsSelection(), HEAD)
        assert [(row.record.seq, row.status) for row in knowns.rows] == [(2, 'current')]
        assert knowns.head == HEAD

    def test_knowns_refuse_an_unknown_investigation(self, service_harness: ServiceHarness) -> None:
        with pytest.raises(UnknownInvestigationError):
            service_harness.service.knowns(UNADDED, KnownsSelection(), HEAD)

    def test_the_listing_names_each_investigation_with_its_latest_round(
        self, filled_harness: ServiceHarness
    ) -> None:
        listed = filled_harness.service.list_rounds()
        assert listed.rows == ((STARTED, 1),)
        assert not listed.older_left_out

    def test_an_investigation_with_no_entries_is_not_listed(
        self, service_harness: ServiceHarness
    ) -> None:
        service_harness.service.start(create_start())
        assert service_harness.service.list_rounds().rows == ()
