"""The closing repository and the closing service over the fakes."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from tests.core.ticket_closing.closing_builders import (
    FAKE_TICKET_ID,
    SERVICE_SLUG,
    ClosingHarness,
)
from tests.core.ticket_closing.fakes import FakeClosingRepository
from tests.core.ticket_closing.service_builders import create_service_harness

if TYPE_CHECKING:
    from mightymodels_core.ticket_closing import CloseRequest

    from tests.core.ticket_closing.service_builders import ServiceHarness


@pytest.fixture
def harness() -> ClosingHarness:
    return ClosingHarness(repository=FakeClosingRepository(), ticket_id=FAKE_TICKET_ID)


@pytest.fixture
def service_harness() -> ServiceHarness:
    return create_service_harness()


@pytest.fixture
def closed_harness(service_harness: ServiceHarness) -> ServiceHarness:
    service_harness.service.close(SERVICE_SLUG, service_harness.request())
    return service_harness


@pytest.fixture
def stale_request(service_harness: ServiceHarness) -> CloseRequest:
    seen = service_harness.service.prepare(SERVICE_SLUG)
    service_harness.tickets.stage(SERVICE_SLUG, replace(seen.section, branch='feat/moved'), ())
    return service_harness.request_for(seen)
