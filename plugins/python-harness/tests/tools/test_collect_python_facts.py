"""collect_python_facts over MCP: the facts report as JSON for paths inside the project."""

import pytest
from mcp import Client
from python_harness.core.output import to_json_value
from python_harness.core.workspace import Workspace
from python_harness.facts.services import build_review_catalog, collect_facts
from python_harness.tools.tests.support import document_of

TOOL = 'collect_python_facts'


@pytest.mark.anyio
class TestCollectPythonFacts:
    PATHS = ('src/shop',)

    async def test_result_is_the_facts_report_as_json(
        self, project_client: Client, shop: Workspace
    ) -> None:
        result = await project_client.call_tool(TOOL, {'paths': list(self.PATHS)})

        expected = collect_facts(shop, self.PATHS, build_review_catalog())
        assert (result.is_error, document_of(result)) == (False, to_json_value(expected))

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        ('paths', 'expected'),
        [
            pytest.param(['src/shop/pricing.py'], ['src/shop/pricing.py'], id='one-file'),
            pytest.param(
                ['src/shop', 'src/shop/pricing.py'],
                ['src/shop/__init__.py', 'src/shop/cli.py', 'src/shop/pricing.py'],
                id='overlapping-paths-report-a-module-once',
            ),
        ],
    )
    async def test_facts_cover_the_given_paths(
        self, project_client: Client, paths: list[str], expected: list[str]
    ) -> None:
        facts = document_of(await project_client.call_tool(TOOL, {'paths': paths}))

        assert [module['path'] for module in facts['modules']] == expected

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        ('option', 'reported'),
        [
            pytest.param({}, False, id='left-out-by-default'),
            pytest.param({'with_function_shapes': True}, True, id='reported-on-request'),
        ],
    )
    async def test_function_shapes_are_reported_only_on_request(
        self, project_client: Client, option: dict[str, bool], reported: bool
    ) -> None:
        arguments = {'paths': ['src/shop/pricing.py'], **option}

        facts = document_of(await project_client.call_tool(TOOL, arguments))

        assert ('function_shape' in facts['modules'][0]['counts']) is reported
