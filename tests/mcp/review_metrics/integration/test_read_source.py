"""Reading a source file from disk gives its text, or nothing when the path cannot be read."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_mcp.review_metrics.sources import read_source

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet


@dataclass(slots=True, kw_only=True, frozen=True)
class SourceCase:
    name: str
    content: bytes | None
    as_directory: bool = False
    text: str | None = None

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def read_source_cases() -> pytest.MarkDecorator:
    readable = SourceCase(name='readable', content=b'x = 1\n', text='x = 1\n')
    undecodable = SourceCase(
        name='undecodable-bytes-are-replaced', content=b'a\xffb\n', text='a�b\n'
    )
    empty = SourceCase(name='empty-file', content=b'', text='')
    missing = SourceCase(name='missing-path', content=None)
    directory = SourceCase(name='directory-path', content=None, as_directory=True)
    return pytest.mark.parametrize(
        'case', [readable.param, undecodable.param, empty.param, missing.param, directory.param]
    )


def path_for(case: SourceCase, tmp_path: Path) -> Path:
    path = tmp_path.joinpath('source.py')
    if case.as_directory:
        path.mkdir()
    elif case.content is not None:
        path.write_bytes(case.content)
    return path


class TestReadSource:
    @read_source_cases()
    def test_the_text_or_nothing_when_the_path_cannot_be_read(
        self, case: SourceCase, tmp_path: Path
    ) -> None:
        assert read_source(path_for(case, tmp_path)) == case.text
