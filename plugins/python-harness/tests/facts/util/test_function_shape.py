"""Function shape and mutable default facts, and the symbols that locate them."""

import pytest
from python_harness.core.sources import ParsedModule
from python_harness.facts.domain import FactKind, FunctionShape
from python_harness.facts.services import collect_module_facts
from python_harness.facts.tests.support import (
    KindsAndLines,
    build_detector_catalog,
    kinds_and_lines,
)
from python_harness.facts.util.function_shape import FUNCTION_SHAPE_DETECTORS

CATALOG = build_detector_catalog(FUNCTION_SHAPE_DETECTORS)


class TestFunctionShapeDetectors:
    @pytest.mark.parametrize(
        ('source', 'expected'),
        [
            pytest.param(
                """
                def load(path):
                    return path


                class Store:
                    def save(self, item):
                        return item
                """,
                ((FactKind.FUNCTION_SHAPE, 1), (FactKind.FUNCTION_SHAPE, 6)),
                id='one-shape-per-function-and-method',
            ),
            pytest.param(
                'def load(paths=[]):\n    return paths\n',
                ((FactKind.FUNCTION_SHAPE, 1), (FactKind.MUTABLE_DEFAULT, 1)),
                id='list-literal-default',
            ),
            pytest.param(
                'def load(*, options=dict()):\n    return options\n',
                ((FactKind.FUNCTION_SHAPE, 1), (FactKind.MUTABLE_DEFAULT, 1)),
                id='dict-call-keyword-default',
            ),
            pytest.param(
                'def load(paths=(), names=frozenset(), limit=None):\n    return paths\n',
                ((FactKind.FUNCTION_SHAPE, 1),),
                id='immutable-defaults',
            ),
        ],
    )
    def test_each_kind_fires_on_its_shape_only(
        self, parsed_module: ParsedModule, expected: KindsAndLines
    ) -> None:
        facts = collect_module_facts(parsed_module, CATALOG).facts

        assert kinds_and_lines(facts) == sorted(expected)

    @pytest.mark.parametrize(
        ('source', 'symbol', 'expected'),
        [
            pytest.param(
                """
                class Store:
                    def save(self, item, /, *rest, flag, **extra) -> None:
                        return None
                """,
                'Store.save',
                FunctionShape(
                    parameters=4,
                    positional=1,
                    statements=1,
                    max_depth=0,
                    is_async=False,
                    returns_annotated=True,
                ),
                id='method-receiver-is-not-a-parameter',
            ),
            pytest.param(
                """
                class Store:
                    @staticmethod
                    def save(item, flag):
                        return item
                """,
                'Store.save',
                FunctionShape(
                    parameters=2,
                    positional=2,
                    statements=1,
                    max_depth=0,
                    is_async=False,
                    returns_annotated=False,
                ),
                id='staticmethod-has-no-receiver',
            ),
            pytest.param(
                """
                async def drain(queue):
                    while queue:
                        if queue.ready:
                            await queue.get()
                        elif queue.closed:
                            for item in queue:
                                item.cancel()
                """,
                'drain',
                FunctionShape(
                    parameters=1,
                    positional=1,
                    statements=6,
                    max_depth=3,
                    is_async=True,
                    returns_annotated=False,
                ),
                id='elif-does-not-deepen-nesting',
            ),
            pytest.param(
                """
                def outer():
                    def inner():
                        if ready:
                            return 1
                        return 2
                    return inner
                """,
                'outer',
                FunctionShape(
                    parameters=0,
                    positional=0,
                    statements=1,
                    max_depth=0,
                    is_async=False,
                    returns_annotated=False,
                ),
                id='nested-definitions-are-not-counted',
            ),
        ],
    )
    def test_shape_detail_describes_the_function(
        self, parsed_module: ParsedModule, symbol: str, expected: FunctionShape
    ) -> None:
        facts = collect_module_facts(parsed_module, CATALOG).facts

        shapes = {fact.symbol: fact.detail for fact in facts}
        assert shapes[symbol] == expected


class TestFunctionSymbols:
    EXPECTED = frozenset({'load', 'load.parse', 'Store.save'})

    @pytest.fixture
    def source(self) -> str:
        return """
            def load():
                def parse():
                    pass


            class Store:
                def save(self):
                    pass
        """

    def test_symbols_are_qualified_by_enclosing_definitions(
        self, parsed_module: ParsedModule
    ) -> None:
        facts = collect_module_facts(parsed_module, CATALOG).facts

        assert frozenset(fact.symbol for fact in facts) == self.EXPECTED
