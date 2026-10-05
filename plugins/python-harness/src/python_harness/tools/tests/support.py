"""A small shop project, and tool results decoded for tests that assert on their JSON."""

import json
from types import MappingProxyType

from mcp.types import CallToolResult

from python_harness.core.tests.support import JsonDocument

SHOP_PROJECT = MappingProxyType(
    {
        'pyproject.toml': """
            [project]
            name = "shop"
            requires-python = ">=3.14"
            [project.scripts]
            shop = "shop.cli:main"
            [build-system]
            requires = ["uv_build"]
            build-backend = "uv_build"
        """,
        'src/shop/__init__.py': '',
        'src/shop/pricing.py': """
            def price(total: int) -> int:
                return total
        """,
        'src/shop/cli.py': """
            from shop.pricing import price


            def main() -> int:
                return price(0)
        """,
        'REVIEW.md': """
            - Location: src/shop/pricing.py:1 `def price(total: int) -> int:`
            - Location: src/shop/pricing.py:40 `return total`
        """,
    }
)


def text_of(result: CallToolResult) -> str:
    return ''.join(getattr(block, 'text', '') for block in result.content)


def document_of(result: CallToolResult) -> JsonDocument:
    return json.loads(text_of(result))
