"""What the review-metrics tool measures and reports, and the limits it holds code to.

`FunctionMetric` and `FileMetric` are what the sources stage measures for one function and one
file. The report models live in `views.py`.
"""

from dataclasses import dataclass
from typing import Literal

LINE_LIMIT = 120
FUNCTION_LOC_LIMIT = 20
PARAM_LIMIT = 3
FILE_LOC_LIMIT = 500
DEPTH_LIMIT = 2
DEFAULT_PACKAGE_DEPTH = 1
DEFAULT_MAX_LISTED = 50

type Graph = dict[str, set[str]]
type Language = Literal['python', 'javascript', 'typescript']


@dataclass(slots=True, kw_only=True, frozen=True)
class FunctionMetric:
    file: str
    name: str
    line: int
    loc: int
    params: int
    bool_params: int
    max_depth: int | None
    approximate: bool = False


@dataclass(slots=True, kw_only=True, frozen=True)
class FileMetric:
    path: str
    language: Language
    loc: int
    long_lines: int
    classes: int = 0
    abstract_classes: int = 0
    is_test: bool = False
    functions: tuple[FunctionMetric, ...] = ()
    imports: tuple[str, ...] = ()
    parsed: bool = True


@dataclass(slots=True, kw_only=True, frozen=True)
class SummaryOptions:
    cap: int = DEFAULT_MAX_LISTED
    depth: int = DEFAULT_PACKAGE_DEPTH
