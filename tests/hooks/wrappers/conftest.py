from typing import TYPE_CHECKING

import pytest

from tests.hooks.wrappers.wrapper_builders import HOOKS_DIR, WrapperRunner

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def hook_runner(tmp_path: Path) -> WrapperRunner:
    return WrapperRunner(
        script=HOOKS_DIR / 'hook.sh',
        workdir=tmp_path,
        launcher_variable='MIGHTYMODELS_HOOK_LAUNCHER',
    )


@pytest.fixture
def dispatch_runner(tmp_path: Path) -> WrapperRunner:
    return WrapperRunner(
        script=HOOKS_DIR / 'dispatch-hook.sh',
        workdir=tmp_path,
        launcher_variable='MIGHTYMODELS_DISPATCH_LAUNCHER',
        timer_variable='MIGHTYMODELS_DISPATCH_SECONDS',
    )
