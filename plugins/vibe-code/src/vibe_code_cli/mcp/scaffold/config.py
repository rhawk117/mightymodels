from vibe_code_cli.mcp.scaffold.spec import Spec
from vibe_code_cli.plugin.manifest import json_text

TIMEOUT_MS = 120_000
NETWORK_URL = 'http://127.0.0.1:8000/mcp'


def render_config(spec: Spec) -> dict[str, str]:
    name = spec.name
    always_load = {'alwaysLoad': True} if spec.always_load else {}
    plugin = {
        'command': 'uv',
        'args': ['run', '--project', f'${{CLAUDE_PLUGIN_ROOT}}/mcp/{name}', name],
    }
    project = {
        'type': 'stdio',
        'command': 'uv',
        'args': ['run', '--project', f'mcp/{name}', name],
        'timeout': TIMEOUT_MS,
    }
    network = {'type': 'http', 'url': NETWORK_URL}
    shapes = {}
    if spec.reach in ('local', 'both'):
        shapes['mcp.plugin.json'] = plugin
        shapes['mcp.project.json'] = project
    if spec.reach in ('network', 'both'):
        shapes['mcp.network.json'] = network
    return {
        filename: json_text({'mcpServers': {name: {**entry, **always_load}}})
        for filename, entry in shapes.items()
    }
