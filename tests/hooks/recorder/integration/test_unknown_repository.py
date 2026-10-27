from typing import TYPE_CHECKING

import pytest
from mightymodels_core.edge import open_state
from mightymodels_core.units_of_work import UnknownRepositoryError, read_entry
from mightymodels_hooks.hook_context import LookupOnlyBackends

from tests.hooks.recorder.recorder_builders import ask_payload, two_answers

if TYPE_CHECKING:
    from tests.hooks.recorder.recorder_builders import RecorderHarness


class TestUnknownRepository:
    async def test_an_answer_in_an_unrecorded_repository_leaves_it_untouched(
        self, harness: RecorderHarness
    ) -> None:
        output = await harness.record(ask_payload(two_answers()))

        assert output is None
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
