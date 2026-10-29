"""What patterns find in a JavaScript or TypeScript file.

The imports are reliable, the function numbers are approximate and each one says so.
"""

import re
from typing import TYPE_CHECKING

from mightymodels_cli.review_metrics.files import count_loc, is_test_path
from mightymodels_cli.review_metrics.shapes import FileMetric, FunctionMetric

if TYPE_CHECKING:
    from pathlib import Path

MIN_CAPTURE_GROUPS = 2
MIN_CAPTURE_GROUPS = 2
OPENING_BRACKETS = '([{<'
CLOSING_BRACKETS = ')]}>'

JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w*{},\s$]+\s+from\s+)?|export\s+[\w*{},\s$]+\s+from\s+|"""
    r"""require\(\s*|import\(\s*)['"]([^'"]+)['"]"""
)
JS_FUNC_RES = (
    re.compile(
        r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([\w$]+)?\s*\(([^)]*)\)'
    ),
    re.compile(
        r'^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s+)?(?:function\s*\*?\s*)?\(([^)]*)\)\s*(?:=>|\{)'
    ),
    re.compile(r'^\s*(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s+)?([\w$]+)\s*=>'),
)
TS_ABSTRACT_RE = re.compile(
    r'^\s*(?:export\s+)?(?:declare\s+)?(?:abstract\s+class|interface)\s+[\w$]+',
    re.MULTILINE,
)
TS_CLASS_RE = re.compile(
    r'^\s*(?:export\s+)?(?:declare\s+)?(?:abstract\s+)?class\s+[\w$]+', re.MULTILINE
)


def js_function_end(lines: list[str], start: int) -> int:
    end = min(start + 1, len(lines) - 1)
    depth = 0
    opened = False
    for idx in range(start, len(lines)):
        line = lines[idx]
        depth += line.count('{') - line.count('}')
        opened = opened or '{' in line
        closed = opened and depth <= 0
        terminated = not opened and line.rstrip().endswith((';', ',')) and idx > start
        if closed or terminated:
            end = idx
            break
    return end


def bracket_step(char: str) -> int:
    if char in OPENING_BRACKETS:
        return 1
    if char in CLOSING_BRACKETS:
        return -1
    return 0


def js_param_stats(raw: str) -> tuple[int, int]:
    raw = raw.strip()
    if not raw:
        return 0, 0
    depth = 0
    count = 1
    for char in raw:
        depth += bracket_step(char)
        if char == ',' and depth == 0:
            count += 1
    bools = len(re.findall(r'(?:=\s*(?:true|false)\b|:\s*boolean\b)', raw))
    return count, min(bools, count)


def typescript_classes(text: str) -> int:
    return len(TS_CLASS_RE.findall(text)) + len(
        re.findall(r'^\s*(?:export\s+)?interface\s+[\w$]+', text, re.MULTILINE)
    )


def analyze_js(rel: Path, text: str, language: str) -> FileMetric:
    loc, long_lines = count_loc(text)
    typed = language == 'typescript'
    lines = text.splitlines()
    found = (js_function(lines, idx, rel) for idx in range(len(lines)))
    return FileMetric(
        path=str(rel),
        language=language,
        loc=loc,
        long_lines=long_lines,
        classes=typescript_classes(text) if typed else 0,
        abstract_classes=len(TS_ABSTRACT_RE.findall(text)) if typed else 0,
        is_test=is_test_path(rel),
        functions=tuple(function for function in found if function is not None),
        imports=tuple(JS_IMPORT_RE.findall(text)),
    )


def js_signature(line: str) -> re.Match[str] | None:
    return next(filter(None, (pattern.match(line) for pattern in JS_FUNC_RES)), None)


def js_function(lines: list[str], idx: int, rel: Path) -> FunctionMetric | None:
    match = js_signature(lines[idx])
    if match is None:
        return None
    captured = (match.lastindex or 0) >= MIN_CAPTURE_GROUPS
    params, bool_params = js_param_stats((match.group(2) if captured else '') or '')
    end = js_function_end(lines, idx)
    return FunctionMetric(
        file=str(rel),
        name=match.group(1) or '<anonymous>',
        line=idx + 1,
        loc=end - idx + 1,
        params=params,
        bool_params=bool_params,
        max_depth=-1,
        approximate=True,
    )
