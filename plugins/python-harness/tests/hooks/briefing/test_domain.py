"""What each file-read outcome answers, with the empty value where it has none."""

import pytest
from python_harness.hooks.briefing.domain import (
    IniDocument,
    IniRead,
    MissingFile,
    TextFile,
    TextRead,
    TomlDocument,
    TomlRead,
    UnreadableFile,
)

UNREADABLE = UnreadableFile('ty.toml', 'is larger than 10 bytes')


class TestReadOutcome:
    @pytest.mark.parametrize(
        ('read', 'expected'),
        [
            pytest.param(MissingFile(), ('', {}, {}, (), False), id='missing'),
            pytest.param(UNREADABLE, ('', {}, {}, (UNREADABLE,), True), id='unreadable'),
            pytest.param(TextFile('3.14\n'), ('3.14\n', {}, {}, (), True), id='text'),
            pytest.param(TomlDocument({'a': 1}), ('', {'a': 1}, {}, (), True), id='toml'),
            pytest.param(IniDocument({'tox': {}}), ('', {}, {'tox': {}}, (), True), id='ini'),
        ],
    )
    def test_an_outcome_answers_with_its_content_or_the_empty_value(
        self, read: TextRead | TomlRead | IniRead, expected: tuple[object, ...]
    ) -> None:
        assert (read.text, read.table, read.sections, read.problems, read.found) == expected
