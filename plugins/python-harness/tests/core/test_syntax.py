"""Shared AST vocabulary: dotted names, receivers and statement and parameter counts."""

import ast
import textwrap

import pytest
from python_harness.core.syntax import (
    FUNCTION_TYPES,
    FunctionDefinition,
    ParameterCounts,
    count_parameters,
    count_statements,
    dotted_name,
    takes_receiver,
)

type PlacedFunction = tuple[FunctionDefinition, ast.AST]


@pytest.fixture
def function(request: pytest.FixtureRequest) -> FunctionDefinition:
    tree = ast.parse(textwrap.dedent(request.param))
    return next(node for node in tree.body if isinstance(node, FUNCTION_TYPES))


class TestDottedName:
    @pytest.fixture
    def expression(self, request: pytest.FixtureRequest) -> ast.expr:
        return ast.parse(request.param, mode='eval').body

    @pytest.mark.parametrize(
        ('expression', 'expected'),
        [
            pytest.param('name', 'name', id='plain-name'),
            pytest.param('os.environ', 'os.environ', id='attribute-chain'),
            pytest.param('make().attribute', None, id='call-in-the-chain'),
            pytest.param('items[0].attribute', None, id='subscript-in-the-chain'),
        ],
        indirect=['expression'],
    )
    def test_only_name_and_attribute_chains_have_a_dotted_name(
        self, expression: ast.expr, expected: str | None
    ) -> None:
        assert dotted_name(expression) == expected


class TestCountStatements:
    @pytest.mark.parametrize(
        ('function', 'expected'),
        [
            pytest.param(
                """
                def run():
                    value = 1
                    return value
                """,
                2,
                id='straight-line-body',
            ),
            pytest.param(
                """
                def run(items):
                    if items:
                        for item in items:
                            item.close()
                    return None
                """,
                4,
                id='statements-inside-blocks-count',
            ),
            pytest.param(
                """
                def run():
                    def helper():
                        return 1
                    class Local:
                        size = 1
                    return helper, Local
                """,
                1,
                id='nested-function-and-class-bodies-excluded',
            ),
            pytest.param(
                """
                def run(ready):
                    if ready:
                        def helper(): ...
                    handler = lambda: 1
                    return handler
                """,
                3,
                id='definitions-inside-blocks-excluded',
            ),
        ],
        indirect=['function'],
    )
    def test_counts_statements_of_the_own_scope(
        self, function: FunctionDefinition, expected: int
    ) -> None:
        assert count_statements(function) == expected


class TestCountParameters:
    @pytest.fixture
    def placed(self, request: pytest.FixtureRequest) -> PlacedFunction:
        tree = ast.parse(textwrap.dedent(request.param))
        classes = (node for node in tree.body if isinstance(node, ast.ClassDef))
        owner = next(classes, tree)
        functions = (node for node in owner.body if isinstance(node, FUNCTION_TYPES))
        return next(functions), owner

    @pytest.mark.parametrize(
        ('placed', 'expected'),
        [
            pytest.param(
                """
                class Store:
                    def save(self, item, /, *rest, flag, **extra): ...
                """,
                ParameterCounts(parameters=4, positional=1),
                id='method-receiver-excluded-variadics-included',
            ),
            pytest.param(
                'def save(self, item, /, *rest, flag, **extra): ...',
                ParameterCounts(parameters=5, positional=2),
                id='first-parameter-kept-outside-a-class',
            ),
            pytest.param(
                """
                class Store:
                    @staticmethod
                    def save(self, item, /, *rest, flag, **extra): ...
                """,
                ParameterCounts(parameters=5, positional=2),
                id='first-parameter-kept-on-a-staticmethod',
            ),
            pytest.param(
                """
                class Store:
                    def collect(*items, **options): ...
                """,
                ParameterCounts(parameters=2, positional=0),
                id='method-without-positional-parameters',
            ),
        ],
        indirect=['placed'],
    )
    def test_counts_every_parameter_kind_and_leaves_out_the_receiver(
        self, placed: PlacedFunction, expected: ParameterCounts
    ) -> None:
        function, parent = placed

        assert count_parameters(function, parent) == expected


class TestTakesReceiver:
    SOURCE = """
        class Store:
            def save(self): ...

            @classmethod
            def create(cls): ...

            @staticmethod
            def build(): ...

            @functools.staticmethod
            def build_dotted(): ...


        def save(self): ...
    """

    @pytest.fixture
    def tree(self) -> ast.Module:
        return ast.parse(textwrap.dedent(self.SOURCE))

    @pytest.fixture
    def store(self, tree: ast.Module) -> ast.ClassDef:
        return next(node for node in tree.body if isinstance(node, ast.ClassDef))

    def function_named(self, owner: ast.Module | ast.ClassDef, name: str) -> FunctionDefinition:
        functions = (item for item in owner.body if isinstance(item, FUNCTION_TYPES))
        return next(item for item in functions if item.name == name)

    @pytest.mark.parametrize(
        ('name', 'expected'),
        [
            pytest.param('save', True, id='instance-method'),
            pytest.param('create', True, id='classmethod'),
            pytest.param('build', False, id='staticmethod'),
            pytest.param('build_dotted', False, id='dotted-staticmethod'),
        ],
    )
    def test_methods_in_the_class_body_take_a_receiver_unless_static(
        self, store: ast.ClassDef, name: str, *, expected: bool
    ) -> None:
        assert takes_receiver(self.function_named(store, name), store) is expected

    def test_function_outside_a_class_body_takes_none(self, tree: ast.Module) -> None:
        assert takes_receiver(self.function_named(tree, 'save'), tree) is False
