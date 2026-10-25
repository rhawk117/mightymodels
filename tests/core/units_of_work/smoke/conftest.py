"""The unit-of-work harness over state opened through open_state."""

from typing import TYPE_CHECKING

import pytest
from anyio.from_thread import start_blocking_portal
from mightymodels_core.edge import open_state
from mightymodels_core.workspace import workspace_at

from tests.core.units_of_work.units_of_work_builders import UnitsOfWorkHarness

if TYPE_CHECKING:
    from collections.abc import Generator

    from tests.core.checkout_builders import StartHarness


@pytest.fixture
def harness(start: StartHarness) -> Generator[UnitsOfWorkHarness]:
    with start_blocking_portal() as portal:
        opened = open_state(start.data_directory, start.toplevel)
        with portal.wrap_async_context_manager(opened) as state:
            yield UnitsOfWorkHarness(
                database=state.database,
                workspace=workspace_at(state.checkout.toplevel),
            )
