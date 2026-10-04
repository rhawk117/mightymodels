#!/usr/bin/env bash
set -eu
mkdir -p fixtures/repo/src/sample fixtures/repo/tests
cat > fixtures/repo/pyproject.toml <<'TOML'
[project]
name = "sample"
version = "0.1.0"
requires-python = ">=3.12"

[dependency-groups]
dev = ["pytest", "ruff"]
TOML
printf '"""Sample package."""\n' > fixtures/repo/src/sample/__init__.py
cat > fixtures/repo/tests/test_sample.py <<'PY'
def test_sample() -> None:
    assert 1 + 1 == 2
PY
