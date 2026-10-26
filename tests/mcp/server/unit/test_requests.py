import pytest
from mightymodels_mcp.server.requests import RequestModel, SlugField
from pydantic import TypeAdapter, ValidationError


class NoteRequest(RequestModel):
    note: str


def refused_slug_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'raw',
        [
            pytest.param('a/b', id='path-separator'),
            pytest.param('..', id='parent-directory'),
            pytest.param('.hidden', id='leading-dot'),
            pytest.param('archives', id='reserved-archive-directory'),
        ],
    )


class TestSlugField:
    adapter = TypeAdapter(SlugField)
    slug = 'mcp-per-action-tools'

    def test_valid_slug_is_accepted(self) -> None:
        assert self.adapter.validate_python(self.slug) == self.slug

    @refused_slug_cases()
    def test_refused_slug_raises_a_validation_error(self, raw: str) -> None:
        with pytest.raises(ValidationError):
            self.adapter.validate_python(raw)

    def test_refusal_carries_core_message(self) -> None:
        with pytest.raises(ValidationError, match='reserved for the archive directory'):
            self.adapter.validate_python('archives')

    def test_schema_publishes_no_pattern(self) -> None:
        assert self.adapter.json_schema() == {'type': 'string'}


class TestRequestModel:
    request = NoteRequest(note='hello')

    def test_extra_field_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            NoteRequest.model_validate({'note': 'hello', 'stray': 1})

    def test_hands_itself_over_as_the_request_argument(self) -> None:
        assert self.request.model_dump_one_level() == {'request': self.request}

    def test_schema_refuses_additional_properties(self) -> None:
        assert NoteRequest.model_json_schema()['additionalProperties'] is False
