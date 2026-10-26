from typing import TYPE_CHECKING

import pytest
from mightymodels_core.schemas.reviews import REVIEW_DISPOSITIONS_OF_RUN, RunLimitParams

from tests.mcp.review.review_harness import DisposeAnswerer, create_review_harness
from tests.mcp.server.server_harness import view_of

if TYPE_CHECKING:
    from tests.mcp.review.review_harness import ReviewHarness
    from tests.mcp.server.server_harness import ServerHarness

FIRST_RUN = 1
LIMIT = 100
BLANK_APPROVERS = ('', '   ')


@pytest.fixture
async def harness(server_harness: ServerHarness) -> ReviewHarness:
    return await create_review_harness(server_harness)


async def approvers(harness: ReviewHarness) -> list[str]:
    async with harness.opener.inner.open() as state:
        with state.database.read() as unit:
            rows = unit.all(
                REVIEW_DISPOSITIONS_OF_RUN, RunLimitParams(review_run_id=FIRST_RUN, limit=LIMIT)
            )
    return [row.by for row in rows]


class TestDisposeApprover:
    @pytest.mark.parametrize('blank', BLANK_APPROVERS)
    async def test_decisions_without_an_approver_are_refused(
        self, harness: ReviewHarness, blank: str
    ) -> None:
        started = await harness.start_with_findings(1)
        arguments = {
            'run_id': started.run_id,
            'decisions': {'F1': {'decision': 'fix'}},
            'by': blank,
        }

        result = await harness.call('review_dispose', arguments)

        assert result.is_error
        assert await approvers(harness) == []

    async def test_decisions_omitting_by_are_refused(self, harness: ReviewHarness) -> None:
        started = await harness.start_with_findings(1)
        arguments = {'run_id': started.run_id, 'decisions': {'F1': {'decision': 'fix'}}}

        result = await harness.call('review_dispose', arguments)

        assert result.is_error

    async def test_decisions_record_the_named_approver(self, harness: ReviewHarness) -> None:
        started = await harness.start_with_findings(1)
        arguments = {
            'run_id': started.run_id,
            'decisions': {'F1': {'decision': 'fix'}},
            'by': 'engineer',
        }

        view_of(await harness.call('review_dispose', arguments))

        assert await approvers(harness) == ['engineer']

    async def test_form_path_records_the_user(self, harness: ReviewHarness) -> None:
        started = await harness.start_with_findings(1)
        answerer = DisposeAnswerer(checked=frozenset({1}))

        view_of(await harness.call('review_dispose', {'run_id': started.run_id}, answerer))

        assert await approvers(harness) == ['user']
