import os

import pytest


@pytest.fixture
def clean_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [name for name in os.environ if name.startswith('GIT_')]:
        monkeypatch.delenv(name)
