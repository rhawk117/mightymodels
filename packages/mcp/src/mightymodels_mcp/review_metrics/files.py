"""Which files are measured, what language each is in, and the line counts and module names.

The walk takes Python, JavaScript and TypeScript files in sorted order and leaves out hidden and
vendored directories, minified and bundled scripts and type declaration files.
"""

from typing import TYPE_CHECKING

from .domain import LINE_LIMIT

if TYPE_CHECKING:
    from pathlib import Path

    from .domain import Language

IGNORED_DIRS = frozenset({
    '.git',
    '.hg',
    '.svn',
    'node_modules',
    '__pycache__',
    '.venv',
    'venv',
    'env',
    '.tox',
    '.mypy_cache',
    '.ruff_cache',
    '.pytest_cache',
    'dist',
    'build',
    '.next',
    '.nuxt',
    'coverage',
    'vendor',
    'target',
    '.idea',
    '.vscode',
    'site-packages',
    '.eggs',
})
PY_SUFFIXES = frozenset({'.py'})
JS_SUFFIXES = frozenset({'.js', '.jsx', '.mjs', '.cjs'})
TS_SUFFIXES = frozenset({'.ts', '.tsx', '.mts', '.cts'})
TEST_DIR_NAMES = frozenset({'test', 'tests', '__tests__', 'spec', 'specs'})


def language_of(path: Path) -> Language | None:
    if path.suffix in PY_SUFFIXES:
        return 'python'
    if path.suffix in JS_SUFFIXES:
        return 'javascript'
    if path.suffix in TS_SUFFIXES:
        return 'typescript'
    return None


def is_test_path(rel: Path) -> bool:
    parts = {p.lower() for p in rel.parts[:-1]}
    if parts & TEST_DIR_NAMES:
        return True
    stem = rel.stem.lower()
    if stem.startswith('test_') or stem.endswith('_test') or stem == 'conftest':
        return True
    return any(marker in rel.name.lower() for marker in ('.spec.', '.test.'))


def iter_source_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or language_of(path) is None:
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIRS or part.startswith('.') for part in rel_parts[:-1]):
            continue
        if path.name.endswith(('.min.js', '.bundle.js', '.d.ts')):
            continue
        found.append(path)
    return found


def count_loc(text: str) -> tuple[int, int]:
    loc = 0
    long_lines = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        loc += 1
        if len(line) > LINE_LIMIT:
            long_lines += 1
    return loc, long_lines


def module_name_for(rel: Path) -> str:
    parts = list(rel.parts)
    parts[-1] = rel.stem
    if parts[-1] in ('__init__', 'index'):
        parts = parts[:-1]
    return '.'.join(parts) if parts else rel.stem
