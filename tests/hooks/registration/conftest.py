from typing import TYPE_CHECKING

import pytest

from tests.hooks.registration.registration_builders import read_registered_hooks

if TYPE_CHECKING:
    from tests.hooks.registration.registration_builders import RegisteredHook


@pytest.fixture(scope='session')
def registered_hooks() -> list[RegisteredHook]:
    return read_registered_hooks()
