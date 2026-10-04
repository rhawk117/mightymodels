import json

from ai_engineer_cli.mcp.scaffold.spec import Spec

TIMEOUT_MS = 120_000
NETWORK_URL = 'http://127.0.0.1:8000/mcp'


def render_config(spec: Spec) -> dict[str, str]:
    """The `.mcp.json` shapes for the spec's reach, keyed by the file name written under config/."""
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
        filename: json.dumps({'mcpServers': {name: {**entry, **always_load}}}, indent=2) + '\n'
        for filename, entry in shapes.items()
    }
