"""Fact details: one detail type per kind, each carrying its kind into the JSON."""

from collections import Counter
from dataclasses import fields
from types import MappingProxyType
from typing import TYPE_CHECKING, get_args

from python_harness.core.output import to_json_value
from python_harness.facts.domain import Fact, FactDetail, FactKind, TryBlock

if TYPE_CHECKING:
    from _typeshed import DataclassInstance


def declared_kind(detail_type: 'type[DataclassInstance]') -> object:
    kind = next(item for item in fields(detail_type) if item.name == 'kind')
    return kind.default


class TestFactDetail:
    DETAIL_TYPES = get_args(FactDetail.__value__)

    def test_each_kind_has_exactly_one_detail_type(self) -> None:
        declared = Counter(declared_kind(item) for item in self.DETAIL_TYPES)

        assert declared == Counter(FactKind)


class TestFactDocument:
    FACT = Fact(4, 'load', TryBlock(handlers=1, statements_in_try=2, caught=('OSError',)))
    EXPECTED = MappingProxyType(
        {
            'line': 4,
            'symbol': 'load',
            'detail': {
                'handlers': 1,
                'statements_in_try': 2,
                'caught': ['OSError'],
                'kind': 'try_block',
            },
        }
    )

    def test_detail_carries_its_kind(self) -> None:
        assert to_json_value(self.FACT) == self.EXPECTED
