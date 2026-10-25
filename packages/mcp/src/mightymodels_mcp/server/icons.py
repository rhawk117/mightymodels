"""Load the packaged SVG icons as MCP icons embedded in data URIs."""

from base64 import b64encode
from importlib.resources import files
from typing import Literal

from mcp.types import Icon

type IconName = Literal[
    'close', 'contract', 'failed_fix', 'review', 'server', 'snapshot', 'task', 'ticket'
]

SVG_MIME_TYPE = 'image/svg+xml'


def load_icon(name: IconName) -> Icon:
    svg = files('mightymodels_mcp').joinpath('assets', f'{name}.svg').read_bytes()
    encoded = b64encode(svg).decode('ascii')
    return Icon(
        src=f'data:{SVG_MIME_TYPE};base64,{encoded}', mime_type=SVG_MIME_TYPE, sizes=['any']
    )
