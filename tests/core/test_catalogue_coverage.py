import ast
import inspect
from pathlib import Path

import mightymodels_core
import pytest
from mightymodels_core import schemas
from mightymodels_core.database import Command, Query


def declared_constants() -> dict[str, str]:
    """Statement name by the constant that holds its declaration, across every schema module."""
    modules = [module for _, module in inspect.getmembers(schemas, inspect.ismodule)]
    return {
        value.name: constant
        for module in modules
        for constant, value in inspect.getmembers(module)
        if isinstance(value, Query | Command) and value in schemas.DECLARATIONS
    }


def names_loaded_by(source: str) -> set[str]:
    return {
        node.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


@pytest.fixture(scope='module')
def production_names() -> set[str]:
    package = Path(inspect.getfile(mightymodels_core)).parent
    sources = [
        path.read_text(encoding='utf-8')
        for path in package.rglob('*.py')
        if 'schemas' not in path.relative_to(package).parts
    ]
    return set().union(*map(names_loaded_by, sources))


def test_every_catalogue_statement_is_used_by_production_code(production_names: set[str]) -> None:
    unused = sorted(
        name for name, constant in declared_constants().items() if constant not in production_names
    )

    assert unused == []
