from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import RedactedTextTooLongError, Slug
from mightymodels_core.ticket_closing import (
    LIVE_DEBUG,
    LiveWorkRemainsError,
    ShippedRequiredError,
    TicketMovedError,
    TooManyGotchasError,
)
from mightymodels_core.tickets import ClosedTicketError, NotStagedError

from tests.core.ticket_closing.closing_builders import (
    ARCHIVE_PATH,
    PLAN_TASK,
    SERVICE_MOMENT,
    SERVICE_SLUG,
    create_branch_facts,
    create_facts,
)
from tests.core.ticket_closing.service_builders import LENGTHENED_LINE, LINKED

if TYPE_CHECKING:
    from mightymodels_core.ticket_closing import CloseRequest

    from tests.core.ticket_closing.service_builders import ServiceHarness


class TestCheck:
    def test_a_ticket_with_no_live_work_is_not_blocked(
        self, service_harness: ServiceHarness
    ) -> None:
        checked = service_harness.service.check(SERVICE_SLUG, create_facts())

        assert (checked.blocked, checked.blockers, checked.git_refusal) == (False, (), None)

    def test_live_work_is_answered_as_a_value_and_nothing_is_written(
        self, service_harness: ServiceHarness
    ) -> None:
        checked = service_harness.service.check(SERVICE_SLUG, create_facts(debug_note=True))

        assert (checked.blocked, checked.blockers) == (True, (LIVE_DEBUG,))
        assert service_harness.status() == 'staged'

    def test_git_not_consulted_is_reported_and_the_branch_is_not_judged(
        self, service_harness: ServiceHarness
    ) -> None:
        facts = replace(
            create_facts(branch=create_branch_facts(unpushed=5)), git_refusal='no git binary'
        )

        checked = service_harness.service.check(SERVICE_SLUG, facts)

        assert (checked.blocked, checked.git_refusal) == (False, 'no git binary')

    def test_a_closed_ticket_is_answered(self, closed_harness: ServiceHarness) -> None:
        checked = closed_harness.service.check(SERVICE_SLUG, create_facts())

        assert checked.blocked is False

    def test_a_ticket_never_staged_is_refused(self, service_harness: ServiceHarness) -> None:
        with pytest.raises(NotStagedError):
            service_harness.service.check(Slug('unstaged-subject'), create_facts())


class TestClose:
    def test_the_ticket_is_marked_closed_and_its_closing_stored(
        self, service_harness: ServiceHarness
    ) -> None:
        closed = service_harness.service.close(SERVICE_SLUG, service_harness.request())

        assert service_harness.status() == 'closed'
        assert service_harness.closings.closing(service_harness.ticket_id) == closed.closing
        assert closed.closing.closed_at == SERVICE_MOMENT
        assert (closed.closing.head, closed.closing.archive) == ('abc1234', ARCHIVE_PATH)
        assert closed.closing.shipped == 'the service'

    def test_the_archive_record_carries_the_work_the_service_read(
        self, service_harness: ServiceHarness
    ) -> None:
        archive = service_harness.service.close(SERVICE_SLUG, service_harness.request()).archive

        assert archive.slug == SERVICE_SLUG
        assert archive.investigations == (LINKED,)
        assert {key: task.status for key, task in archive.tasks.items()} == {PLAN_TASK: 'verified'}
        assert [(item.key, item.outcome) for item in archive.verification] == [
            ('T1.AC-1', 'never-run')
        ]
        assert [(item.text, item.origin) for item in archive.decisions] == [
            ('use a policy', 'linked-probe e1')
        ]
        assert archive.review is not None
        assert archive.review.by_decision == {'fixed': ('F1',), 'dismiss': ('F2',)}

    def test_git_not_consulted_closes_the_ticket_with_no_head(
        self, service_harness: ServiceHarness
    ) -> None:
        facts = replace(create_facts(), git_refusal='no git binary', head=None, branch=None)

        closed = service_harness.service.close(SERVICE_SLUG, service_harness.request(facts=facts))

        assert closed.closing.head is None
        assert service_harness.status() == 'closed'

    def test_live_work_refuses_the_close_and_writes_nothing(
        self, service_harness: ServiceHarness
    ) -> None:
        request = service_harness.request(facts=create_facts(debug_note=True))

        with pytest.raises(LiveWorkRemainsError) as refused:
            service_harness.service.close(SERVICE_SLUG, request)

        assert refused.value.blockers == (LIVE_DEBUG,)
        assert service_harness.status() == 'staged'
        assert service_harness.closings.closing(service_harness.ticket_id) is None

    def test_a_ticket_that_moved_while_git_was_asked_is_refused_and_nothing_is_written(
        self, service_harness: ServiceHarness, stale_request: CloseRequest
    ) -> None:
        with pytest.raises(TicketMovedError) as refused:
            service_harness.service.close(SERVICE_SLUG, stale_request)

        assert refused.value.changed == ('branch',)
        assert service_harness.status() == 'staged'
        assert service_harness.closings.closing(service_harness.ticket_id) is None

    def test_a_blank_shipped_line_is_refused_and_nothing_is_written(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(ShippedRequiredError):
            service_harness.service.close(SERVICE_SLUG, service_harness.request(shipped=' \n '))

        assert service_harness.status() == 'staged'

    def test_a_fourth_gotcha_is_refused_and_nothing_is_written(
        self, service_harness: ServiceHarness
    ) -> None:
        request = service_harness.request()
        lines = replace(request.lines, gotchas=('a', 'b', 'c', 'd'))

        with pytest.raises(TooManyGotchasError):
            service_harness.service.close(SERVICE_SLUG, replace(request, lines=lines))

        assert service_harness.closings.closing(service_harness.ticket_id) is None

    def test_a_line_that_redaction_lengthens_past_its_limit_is_refused(
        self, service_harness: ServiceHarness
    ) -> None:
        request = service_harness.request(shipped=LENGTHENED_LINE)

        with pytest.raises(RedactedTextTooLongError):
            service_harness.service.close(SERVICE_SLUG, request)

        assert service_harness.status() == 'staged'

    def test_a_closed_ticket_cannot_be_closed_again(self, closed_harness: ServiceHarness) -> None:
        with pytest.raises(ClosedTicketError):
            closed_harness.service.close(SERVICE_SLUG, closed_harness.request())
