"""A generic typed adapter over stdlib `sqlite3`. It names no mightymodels table."""

from .catalogue import Catalogue, bind_catalogue, parse_blocks
from .codec import bind_params, create_row_decoder, decode_row
from .errors import (
    DatabaseError,
    DuplicateBlockError,
    DuplicateDeclarationError,
    EmptyBlockError,
    MissingBlockError,
    NaiveTimestampError,
    RowDecodeError,
    UndeclaredBlockError,
)
from .statements import Command, Declaration, Query

__all__ = [
    'Catalogue',
    'Command',
    'DatabaseError',
    'Declaration',
    'DuplicateBlockError',
    'DuplicateDeclarationError',
    'EmptyBlockError',
    'MissingBlockError',
    'NaiveTimestampError',
    'Query',
    'RowDecodeError',
    'UndeclaredBlockError',
    'bind_catalogue',
    'bind_params',
    'create_row_decoder',
    'decode_row',
    'parse_blocks',
]
