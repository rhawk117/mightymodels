from typing import TYPE_CHECKING

import pytest
from mightymodels_core.edge import open_state
from mightymodels_core.units_of_work import UnknownRepositoryError, read_entry
from mightymodels_hooks.hook_context import LookupOnlyBackends

if TYPE_CHECKING:
    from tests.hooks.session_start.integration.conftest import SessionStartHarness


class TestUnknownRepository:
    async def test_session_start_leaves_an_unrecorded_repository_untouched(
        self, harness: SessionStartHarness
    ) -> None:
        await harness.handler().handle({'cwd': str(harness.checkout)})

        exclude = harness.checkout.joinpath('.git', 'info', 'exclude')
        assert not exclude.is_file() or '.mightymodels' not in exclude.read_text(encoding='utf-8')
        async with open_state(
            harness.data_directory, harness.checkout, backends=LookupOnlyBackends()
        ) as state:
            with (
                pytest.raises(UnknownRepositoryError),
                read_entry(state.database, state.checkout.repository_key()),
            ):
                pass
        assert harness.stderr.getvalue() == ''
