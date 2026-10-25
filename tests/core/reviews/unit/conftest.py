"""The review and decision repositories over the fakes."""

from typing import TYPE_CHECKING

import pytest

from tests.core.reviews.review_builders import open_fake_harness

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from tests.core.reviews.review_builders import HarnessOpener, ReviewHarness


@pytest.fixture(scope='session')
def open_harness() -> HarnessOpener:
    return open_fake_harness


@pytest.fixture
def harness(open_harness: HarnessOpener, tmp_path: Path) -> Generator[ReviewHarness]:
    with open_harness(tmp_path) as opened:
        yield opened
