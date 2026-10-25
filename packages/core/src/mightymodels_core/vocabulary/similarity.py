"""The similarity vocabulary: the kinds of row the index holds and the scouts that report."""

from typing import Literal

type SimilarityKind = Literal['ledger-entry', 'scout-report', 'review-finding', 'crashout']


type Scout = Literal['code-scout', 'web-scout']
