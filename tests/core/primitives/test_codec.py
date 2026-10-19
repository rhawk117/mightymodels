import msgspec
import pytest
from mightymodels_core.primitives import (
    StateError,
    UnreadableJsonError,
    decode_text,
    encode_compact,
    encode_indented,
)


@pytest.fixture
def value() -> dict[str, object]:
    return {'name': 'café', 'items': [1, 2]}


class TestEncoding:
    def test_compact_has_nothing_between_tokens(self, value: dict[str, object]) -> None:
        assert encode_compact(value) == '{"name":"café","items":[1,2]}'.encode()

    def test_indented_uses_two_spaces(self, value: dict[str, object]) -> None:
        text = encode_indented(value).decode()

        assert text.startswith('{\n  "name": "café"')
        assert not text.endswith('\n')

    def test_both_forms_decode_to_the_same_value(self, value: dict[str, object]) -> None:
        assert decode_text(encode_indented(value).decode()) == value
        assert decode_text(encode_compact(value).decode()) == value


class TestDecodeFailure:
    @pytest.mark.parametrize('text', ['{"a":', 'NaN', '[1] [2]', ''])
    def test_malformed_json_raises_unreadable_json(self, text: str) -> None:
        with pytest.raises(UnreadableJsonError) as raised:
            decode_text(text)

        assert isinstance(raised.value.__cause__, msgspec.DecodeError)

    def test_error_is_a_direct_state_error_subclass(self) -> None:
        assert UnreadableJsonError.__bases__ == (StateError,)

    def test_lone_surrogate_text_raises_unreadable_json(self) -> None:
        with pytest.raises(UnreadableJsonError):
            decode_text('"\ud800"')
