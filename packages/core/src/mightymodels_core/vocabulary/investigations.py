"""The investigation vocabulary: ledger entry kinds and sources."""

from typing import Literal

type EntryKind = Literal['known', 'open', 'decision', 'resource', 'next']


type EntrySource = Literal['code-scout', 'web-scout', 'user', 'primary']
