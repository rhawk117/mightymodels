# mightymodels: agent instructions

## Commands

Every command goes through `make`. Each target delegates to uv, prek or a script under `scripts/`.

- `make setup` installs the prek git hooks and syncs every workspace package and dependency group. A fresh clone has no git hook, so run it before the first commit.
- `make sync` syncs the workspace packages and dependency groups.
- `make format` runs the prek hooks in the `format` group on all files: the hygiene fixers, uv-lock, ruff fix and format, shfmt and mdformat.
- `make lint` runs the prek hooks in the `lint` group on all files: the hygiene checks, ruff check, ty and shellcheck.
- `make typecheck` runs ty alone.
- `make test` runs `pytest -q -m "unit or agents or smoke"`, with coverage.
- `make test.end-to-end` runs `pytest -q -m e2e`.
- `make pre-commit` runs every prek hook in `.pre-commit-config.yaml` on all files.
- `make check` runs lint, then test.
- `make quality` runs every prek hook on all files, then `pytest -q -m "not integration"`, which matches CI's quality job.

## Stack

Python 3.14 (`requires-python` in `pyproject.toml`), uv, ruff, ty, pytest, mdformat and prek. `.github/workflows/ci.yml` sets up CI: `astral-sh/setup-uv` takes its uv version from the `UV_VERSION` repository variable, and `actions/setup-node` takes its Node version from the `NODE_VERSION` repository variable.

## Layout

- The plugin sits at the repository root, and `.claude-plugin/plugin.json` contains its manifest. The root `pyproject.toml` is both the plugin project and the uv workspace root, with members under `packages/`.
- `packages/hooks` holds the plugin's hook code (`mightymodels_hooks`), which `hooks/hooks.json` runs through the shell wrappers in `hooks/`. `.claude/hooks/pyhooks.py` is the project's own hook script, a PEP 723 script that `.claude/settings.json` wires to Write, Edit and Read. ty does not check it, because `ty.toml` includes only `packages` and `tests`. The plugin's hooks record and route, and refuse only a dispatch outside the caller's roster, an intern dispatch unless a task is started for the intern and every such task owns exactly one file, a dispatch of the engineer or architect from the main thread while the branch's only unclosed ticket has no task in progress (with several unclosed tickets the hook warns instead of refusing), a dispatch whose task or ticket state cannot be read (it fails closed), and a payload that is malformed or names no target type (exit 2). When the hook itself cannot run (the launcher crashes or times out), it refuses any dispatch made by a plugin worker, and any dispatch of the engineer, architect or intern while the project has a `.mightymodels/` directory.
- `packages/mcp` also holds the `review_metrics` and `review_signals` tool domains, which carry the review commands that the removed command line used to run.
- Read `.claude/rules/python.md` before writing Python and `.claude/rules/testing.md` before writing tests. Both load on their own when you touch a matching file.

## Conventions

- Commit subjects follow Conventional Commits as the history does: `type(scope): subject`, with the subject in lowercase imperative and no closing period. The types in use are feat, fix, ci, build, style and docs.
- The plugin version lives in both `pyproject.toml` and `.claude-plugin/plugin.json`. `tests/test_release_metadata.py` fails when they differ, and the release workflow (`.github/workflows/cd.yml`) bumps both.

## Boundaries

- Always: run the Verification commands before calling work done.
- Ask first: edits to `pyproject.toml`, `uv.lock`, `ruff.toml`, `pytest.toml` and `ty.toml`, which `.claude/settings.json` lists under `permissions.ask`; version bumps, which the release workflow owns; changes to `.claude/settings.json` or `.claude/hooks/pyhooks.py`, because every session runs the hooks they define.
- Never: weaken the ruff or ty configuration; hand-edit `uv.lock`, which the uv-lock hook regenerates; commit `.mightymodels/`, which stays a local-only git exclusion (`SECURITY.md`).

## Verification

`.github/workflows/ci.yml` defines CI's quality job, which runs every prek hook on all files and then the tests. Match it with `make pre-commit`, then `uv run pytest -q -m "not integration"`, because `make test` skips the e2e tests and the unmarked tests that CI runs. CI's integration job runs `pytest -q -m integration`. `make check` is the faster local loop, but it skips the `format` group (the hygiene fixers, uv-lock, shfmt and mdformat), so it can pass where CI fails.

## Claude Code

- Inside the Bash sandbox, whole-tree checks (`make lint`, `make check`, `make pre-commit`) can fail on sandbox mount points such as `.mcp.json` or `.claude/skills`, which show up as character devices. A failure that names one of those paths comes from the sandbox, not the repository: report it rather than changing code to get past it.
- The project hooks run on every tool call: before a Write or Edit, a check asks for approval when the change adds a lint or type suppression; after it, the formatter runs; after a Read, ruff and ty report diagnostics on the file.
