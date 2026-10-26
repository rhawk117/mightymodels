from mightymodels_hooks.session_pointer import SLUG_BEARING_TOOLS, TOOL_FIELDS
from mightymodels_mcp.main import create_catalog

POINTER_FIELDS = ('slug', 'ticket', 'investigation_id')


class TestSlugBearingTools:
    def test_the_list_equals_the_server_tools_with_a_pointer_field(self) -> None:
        bearing: dict[str, str] = {}
        for tool in create_catalog().list_tools():
            properties = tool.parameters.get('properties', {})
            fields = [name for name in POINTER_FIELDS if name in properties]
            if fields:
                bearing[tool.name] = fields[0]

        assert set(SLUG_BEARING_TOOLS) == set(bearing)
        assert dict(TOOL_FIELDS) == bearing
