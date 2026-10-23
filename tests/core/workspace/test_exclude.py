"""The state-directory entry in the repository's `info/exclude`."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.workspace import EXCLUDE_LINE, exclude_state

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet


@dataclass(slots=True, kw_only=True, frozen=True)
class ExistingExclude:
    name: str
    current: str | None
    expected: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=(pytest.mark.integration,))


def exclude_existing_content_cases() -> pytest.MarkDecorator:
    scenarios = [
        ExistingExclude(name='absent', current=None, expected=f'{EXCLUDE_LINE}\n'),
        ExistingExclude(name='empty', current='', expected=f'{EXCLUDE_LINE}\n'),
        ExistingExclude(
            name='newline-ended', current='*.log\n', expected=f'*.log\n{EXCLUDE_LINE}\n'
        ),
        ExistingExclude(name='unended', current='*.log', expected=f'*.log\n{EXCLUDE_LINE}\n'),
        ExistingExclude(
            name='already-listed',
            current=f'*.log\n{EXCLUDE_LINE}\n',
            expected=f'*.log\n{EXCLUDE_LINE}\n',
        ),
    ]
    return pytest.mark.parametrize('existing', [scenario.param for scenario in scenarios])


class TestExcludeState:
    @pytest.fixture
    def common_directory(self, existing: ExistingExclude, tmp_path: Path) -> Path:
        directory = tmp_path.joinpath('common')
        directory.mkdir()
        if existing.current is not None:
            directory.joinpath('info').mkdir()
            directory.joinpath('info', 'exclude').write_text(existing.current, encoding='utf-8')
        return directory

    @exclude_existing_content_cases()
    def test_the_state_directory_is_listed_once(
        self, common_directory: Path, existing: ExistingExclude
    ) -> None:
        exclude_state(common_directory)
        exclude_state(common_directory)

        written = common_directory.joinpath('info', 'exclude').read_text(encoding='utf-8')
        assert written == existing.expected
