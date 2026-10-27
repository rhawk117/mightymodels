import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.hooks.pre_compact.pre_compact_builders import PreCompactHarness


class TestPreCompact:
    async def test_the_ticket_on_the_branch_gets_both_files(
        self, ticketed: PreCompactHarness
    ) -> None:
        output = await ticketed.compact()
        record = json.loads(ticketed.handoffs.joinpath('snapshot.json').read_text('utf-8'))
        markdown = ticketed.handoffs.joinpath('snapshot.md').read_text('utf-8')
        assert output is None
        assert record['slug'] == 'port-it'
        assert 'port-it' in markdown
        assert ticketed.stderr.getvalue() == ''

    async def test_a_branch_no_ticket_names_writes_nothing(
        self, ticketed_elsewhere: PreCompactHarness
    ) -> None:
        output = await ticketed_elsewhere.compact()
        assert output is None
        assert ticketed_elsewhere.written() == []
        assert ticketed_elsewhere.stderr.getvalue() == ''

    async def test_a_repository_with_no_state_writes_nothing(
        self, harness: PreCompactHarness
    ) -> None:
        output = await harness.compact()
        assert output is None
        assert harness.written() == []
