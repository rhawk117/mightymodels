"""Top-level symbol discovery from module statements."""

import pytest
from python_harness.calls.domain import SymbolKind
from python_harness.calls.util.symbols import top_level_symbols
from python_harness.core.sources import ParsedModule, load_sources
from python_harness.core.tests.fixtures import ProjectBuilder


class TestTopLevelSymbols:
    SOURCE = """
        import os

        __all__ = ['run']
        LIMIT = 3
        first, second = 1, 2
        timeout: float = 1.5
        type Port = int


        def run() -> None:
            def helper() -> None: ...


        async def serve() -> None: ...


        class Server:
            name = 'server'
    """
    EXPECTED = (
        ('LIMIT', SymbolKind.CONSTANT, 4),
        ('timeout', SymbolKind.CONSTANT, 6),
        ('Port', SymbolKind.CONSTANT, 7),
        ('run', SymbolKind.FUNCTION, 10),
        ('serve', SymbolKind.FUNCTION, 14),
        ('Server', SymbolKind.CLASS, 17),
    )

    @pytest.fixture
    def module(self, project_builder: ProjectBuilder) -> ParsedModule:
        workspace = project_builder.write({'pkg/server.py': self.SOURCE})
        return load_sources(workspace, workspace.python_files('pkg')).modules[0]

    def test_module_body_definitions_become_symbols(self, module: ParsedModule) -> None:
        symbols = top_level_symbols(module, 'pkg.server')

        described = tuple((item.name, item.kind, item.line) for item in symbols)
        assert described == self.EXPECTED

    def test_symbols_carry_their_qualified_name(self, module: ParsedModule) -> None:
        symbols = top_level_symbols(module, 'pkg.server')

        assert symbols[0].qualified_name() == 'pkg.server.LIMIT'
