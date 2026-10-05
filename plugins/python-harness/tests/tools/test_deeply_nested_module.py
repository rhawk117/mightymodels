"""One module too deeply nested to walk is reported, and does not fail the project tools."""

import pytest
from mcp import Client
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.tools.tests.support import document_of

DEEP = 'src/deep/chain.py'
SIBLING = 'src/deep/plain.py'


@pytest.fixture
def deep_project(project_builder: ProjectBuilder) -> None:
    project_builder.write(
        {DEEP: 'x = a' + '.b' * 3000 + '\n', SIBLING: 'def plain() -> int:\n    return 1\n'}
    )


@pytest.mark.anyio
@pytest.mark.usefixtures('deep_project')
class TestDeeplyNestedModule:
    async def test_facts_list_the_module_as_unparsable(self, project_client: Client) -> None:
        result = await project_client.call_tool('collect_python_facts', {'paths': ['src/deep']})

        facts = document_of(result)
        assert (result.is_error, [item['path'] for item in facts['unparsable']]) == (False, [DEEP])

    async def test_calls_still_answer_for_a_sibling(self, project_client: Client) -> None:
        result = await project_client.call_tool('map_python_calls', {'paths': [SIBLING]})

        calls = document_of(result)
        assert (result.is_error, [item['metrics']['path'] for item in calls['modules']]) == (
            False,
            [SIBLING],
        )
