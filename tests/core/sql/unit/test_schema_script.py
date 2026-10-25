import re

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from tests.core.sql.sql_builders import SCHEMA, strip_comments

CONSTRAINT_PREFIXES = {
    'PRIMARY KEY': 'pk_',
    'FOREIGN KEY': 'fk_',
    'UNIQUE': 'uq_',
    'CHECK': 'ck_',
}


@pytest.fixture(scope='module')
def script() -> str:
    return strip_comments(SCHEMA.read_text(encoding='utf-8'))


class TestSchemaScript:
    keywords = st.sampled_from(list(CONSTRAINT_PREFIXES))

    def test_every_index_is_named_with_its_prefix(self, script: str) -> None:
        names = re.findall(r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\w+)', script)
        assert names
        assert [name for name in names if not name.startswith('ix_')] == []

    @given(keyword=keywords)
    @example(keyword='PRIMARY KEY')
    @example(keyword='FOREIGN KEY')
    @example(keyword='UNIQUE')
    @example(keyword='CHECK')
    def test_every_constraint_is_named_with_its_prefix(self, script: str, keyword: str) -> None:
        prefix = CONSTRAINT_PREFIXES[keyword]
        named = re.findall(rf'CONSTRAINT\s+(\w+)\s+{keyword}\b', script)
        declared = re.findall(rf'\b{keyword}\b', script)
        assert len(named) == len(declared)
        assert [name for name in named if not name.startswith(prefix)] == []
