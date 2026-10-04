# __NAME__

__DESCRIPTION__

## Run

```sh
uv sync
uv run __NAME__ --root .
```

## Check

```sh
uv run ruff check . && uv run ruff format --check .
uv run ty check
uv run pytest
```

## Add a tool

Create `src/__PKG__/tools/<tool_name>/schema.py` (Pydantic `Input` and `Output`) and `use_case.py` (`run(workspace, params) -> Output`), then register it in `src/__PKG__/server.py` next to the existing tools and add a test in `tests/`.
