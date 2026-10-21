"""One checkout in `tmp_path`, its state directory and a directory outside it."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import Slug

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet

TICKET = Slug('alpha-ticket')


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    directory = tmp_path.joinpath('checkout')
    directory.mkdir()
    return directory


@pytest.fixture
def state(checkout: Path) -> Path:
    directory = checkout.joinpath('.mightymodels')
    directory.mkdir()
    return directory


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    directory = tmp_path.joinpath('outside')
    directory.mkdir()
    return directory


@dataclass(slots=True, kw_only=True, frozen=True)
class SyntaxRefusal:
    name: str
    source: str
    line: int
    reason: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


@dataclass(slots=True, kw_only=True, frozen=True)
class TypeRefusal:
    name: str
    source: str
    key_path: str
    line: int | None

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)
