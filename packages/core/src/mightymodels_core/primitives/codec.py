"""JSON encoding and decoding on msgspec alone.

The encoders take any value msgspec encodes and return UTF-8 bytes with no trailing newline: the
compact form has nothing between its tokens, the indented form uses `INDENT` spaces. `decode_text`
reads one JSON document into plain values and raises `UnreadableJsonError` for whatever msgspec
refuses.
"""

import msgspec

from .errors import UnreadableJsonError

INDENT = 2


def encode_compact(value: object) -> bytes:
    return msgspec.json.encode(value)


def encode_indented(value: object) -> bytes:
    return msgspec.json.format(msgspec.json.encode(value), indent=INDENT)


def decode_text(text: str) -> object:
    try:
        return msgspec.json.decode(text)
    except (msgspec.DecodeError, UnicodeEncodeError) as error:
        raise UnreadableJsonError(detail=str(error)) from error
