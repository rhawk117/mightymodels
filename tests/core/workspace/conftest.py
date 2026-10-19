"""One checkout in `tmp_path`, its state directory and a directory outside it."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import Slug

if TYPE_CHECKING:
    from pathlib import Path

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
