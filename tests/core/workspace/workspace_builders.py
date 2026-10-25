"""Test-local ticket slug, refusal scenarios and character strategies for the workspace tests."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from hypothesis import strategies as st
from mightymodels_core.primitives import Slug

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

TICKET = Slug('alpha-ticket')

LONE_SURROGATES = st.characters(categories=['Cs'])
CONTROL_CHARACTERS = st.characters(categories=['Cc'], exclude_characters='\t\n\r')
NAMED_UNREADABLE_CHARACTERS = st.sampled_from(['\u2028', '\u2029', '\ufffe', '\uffff'])
ESCAPED_CHARACTERS = st.one_of(CONTROL_CHARACTERS, NAMED_UNREADABLE_CHARACTERS)
REFUSED_CHARACTERS = st.one_of(ESCAPED_CHARACTERS, LONE_SURROGATES)


@dataclass(slots=True, kw_only=True, frozen=True)
class SyntaxRefusal:
    name: str
    source: str
    line: int
    reason: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


@dataclass(slots=True, kw_only=True, frozen=True)
class TypeRefusal:
    name: str
    source: str
    key_path: str
    line: int | None

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)
