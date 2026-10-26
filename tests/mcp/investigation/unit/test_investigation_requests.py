from typing import Any

import pytest
from mightymodels_core.investigations.ledger import KNOWNS_LIMIT, SECTION_KINDS
from mightymodels_mcp.investigation.schemas import (
    InvestigationAddRequest,
    InvestigationKnownsRequest,
    InvestigationListRequest,
    InvestigationRenderRequest,
    InvestigationStartRequest,
    LedgerEntry,
)
from pydantic import ValidationError

ID = 'probe-investigation'
ENTRY = {'kind': 'known', 'text': 'a fact', 'source': 'code-scout', 'cite': 'a.py:1'}


class TestStartRequest:
    def test_kind_defaults_to_none(self) -> None:
        request = InvestigationStartRequest.model_validate({'target': 'why'})

        assert (request.target, request.kind) == ('why', None)

    def test_kind_is_taken(self) -> None:
        request = InvestigationStartRequest.model_validate({'target': 'why', 'kind': 'claim'})

        assert request.kind == 'claim'

    @pytest.mark.parametrize(
        'given',
        [
            pytest.param({}, id='no-target'),
            pytest.param({'target': 'why', 'kind': 'galaxy'}, id='kind'),
            pytest.param({'target': 'why', 'unknown': 1}, id='extra'),
        ],
    )
    def test_invalid_start_is_refused(self, given: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            InvestigationStartRequest.model_validate(given)


class TestAddRequest:
    def test_entries_default_their_optional_fields(self) -> None:
        request = InvestigationAddRequest.model_validate({
            'investigation_id': ID,
            'round': 1,
            'entries': [{'kind': 'open', 'text': 'q', 'source': 'user'}],
        })

        entry = request.entries[0]
        assert (entry.cite, entry.supersedes) == (None, ())
        assert (request.investigation_id, request.round) == (ID, 1)

    def test_cite_is_stripped(self) -> None:
        entry = LedgerEntry.model_validate({**ENTRY, 'cite': '  a.py:1  ', 'supersedes': [1]})

        assert (entry.cite, entry.supersedes) == ('a.py:1', (1,))

    @pytest.mark.parametrize(
        'given',
        [
            pytest.param({'investigation_id': 'Not A Slug'}, id='slug'),
            pytest.param({'unknown': 1}, id='extra'),
            pytest.param({'entries': [{**ENTRY, 'unknown': 1}]}, id='entry-key'),
            pytest.param({'entries': [{**ENTRY, 'kind': 'target'}]}, id='target-entry'),
            pytest.param({'entries': [{**ENTRY, 'cite': '   '}]}, id='blank-cite'),
            pytest.param({'entries': [{**ENTRY, 'source': 'nobody'}]}, id='source'),
        ],
    )
    def test_invalid_add_is_refused(self, given: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            InvestigationAddRequest.model_validate({
                'investigation_id': ID,
                'round': 1,
                'entries': [ENTRY],
                **given,
            })


class TestKnownsRequest:
    def test_defaults_are_cores(self) -> None:
        request = InvestigationKnownsRequest.model_validate({'investigation_id': ID})

        assert (request.kinds, request.limit) == (SECTION_KINDS, KNOWNS_LIMIT)

    def test_kinds_and_limit_are_taken(self) -> None:
        request = InvestigationKnownsRequest.model_validate({
            'investigation_id': ID,
            'kinds': ['next'],
            'limit': 3,
        })

        assert (request.kinds, request.limit) == (('next',), 3)

    @pytest.mark.parametrize(
        'given',
        [
            pytest.param({'kinds': []}, id='empty-kinds'),
            pytest.param({'kinds': ['target']}, id='target-kind'),
            pytest.param({'limit': 0}, id='limit-zero'),
            pytest.param({'investigation_id': ''}, id='slug'),
            pytest.param({'unknown': 1}, id='extra'),
        ],
    )
    def test_invalid_knowns_is_refused(self, given: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            InvestigationKnownsRequest.model_validate({'investigation_id': ID, **given})


class TestIdOnlyRequests:
    def test_render_takes_an_id(self) -> None:
        request = InvestigationRenderRequest.model_validate({'investigation_id': ID})

        assert request.investigation_id == ID

    def test_render_refuses_a_bad_id(self) -> None:
        with pytest.raises(ValidationError):
            InvestigationRenderRequest.model_validate({'investigation_id': 'A B'})

    def test_list_takes_nothing(self) -> None:
        assert InvestigationListRequest.model_validate({}).model_dump() == {}
        with pytest.raises(ValidationError):
            InvestigationListRequest.model_validate({'unknown': 1})
