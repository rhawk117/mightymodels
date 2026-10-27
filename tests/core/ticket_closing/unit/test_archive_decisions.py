from typing import TYPE_CHECKING

from mightymodels_core.primitives import redact
from mightymodels_core.ticket_decisions import IncomingDecision

from tests.core.ticket_closing.closing_builders import SERVICE_SLUG

if TYPE_CHECKING:
    from tests.core.ticket_closing.service_builders import ServiceHarness


class TestArchivedTicketDecisions:
    def test_ticket_decisions_follow_the_ledger_decisions_as_one_redacted_line(
        self, service_harness: ServiceHarness
    ) -> None:
        decisions = service_harness.ticket_decisions
        decisions.add(
            service_harness.ticket_id,
            IncomingDecision(
                question='Which store?', answer='Other', response='sqlite\npassword=hunter2'
            ),
        )
        decisions.add(
            service_harness.ticket_id, IncomingDecision(question='Ship now?', answer='Yes')
        )

        archive = service_harness.service.close(SERVICE_SLUG, service_harness.request()).archive

        assert [(item.text, item.origin) for item in archive.decisions] == [
            ('use a policy', 'linked-probe e1'),
            (redact('Which store?: Other - sqlite password=hunter2'), 'ticket'),
            ('Ship now?: Yes', 'ticket'),
        ]
        assert 'hunter2' not in archive.decisions[1].text

    def test_the_decisions_are_cut_to_the_limit_keeping_the_last(
        self, service_harness: ServiceHarness
    ) -> None:
        for number in range(1, 5):
            service_harness.ticket_decisions.add(
                service_harness.ticket_id, IncomingDecision(question=f'Q{number}', answer='A')
            )

        archive = service_harness.service.close(SERVICE_SLUG, service_harness.request()).archive

        assert [item.text for item in archive.decisions] == ['Q1: A', 'Q2: A', 'Q3: A', 'Q4: A']
