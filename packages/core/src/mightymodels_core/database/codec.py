"""Binding parameter Structs to named placeholders and decoding `json_object` rows into row Structs.

Lists, dicts and Structs bind as JSON text, aware datetimes as whole seconds since the epoch,
and everything else as itself. A row is the single JSON text a statement selects.
"""

from datetime import datetime
from math import floor
from typing import TYPE_CHECKING

import msgspec
from msgspec import Struct

from .errors import NaiveTimestampError, RowDecodeError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .statements import Query


def bind_value(field: str, value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise NaiveTimestampError(field=field)

        return floor(value.timestamp())

    if isinstance(value, list | dict | Struct):
        return msgspec.json.encode(value).decode()

    return value


def bind_params(params: Struct) -> dict[str, object]:
    return {
        field: bind_value(field, value) for field, value in msgspec.structs.asdict(params).items()
    }


def create_row_decoder[R: Struct](row: type[R]) -> msgspec.json.Decoder[R]:
    return msgspec.json.Decoder(row, strict=False)


def decode_rows[P: Struct, R: Struct](query: Query[P, R], rows: Iterable[str]) -> list[R]:
    decoder = create_row_decoder(query.row)
    try:
        return [decoder.decode(row) for row in rows]
    except msgspec.DecodeError as error:
        raise RowDecodeError(statement=query.name, detail=str(error)) from error


def decode_row[P: Struct, R: Struct](query: Query[P, R], row: str) -> R:
    return decode_rows(query, [row])[0]
