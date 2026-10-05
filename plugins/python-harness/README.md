# pythonista

A Claude Code plugin for Python engineering. It ships:

| Component | Path | What it does |
| --- | --- | --- |
| Skill `what-would-ryan-say` | `skills/what-would-ryan-say/` | `/pythonista:what-would-ryan-say pr <num\|branch> \| codebase [path]  report \| plan`: reviews Python against Ryan's guide and philosophy, writes `PYTHON-REVIEW.md` or `REFACTOR-PLAN.md`, never edits code. Runs only when you type it. |
| Agent `pylens` | `agents/pylens.md` | Read-only fact gatherer (`Read`, `Grep`, `Glob`) on Haiku, dispatched by the skill as `pythonista:pylens`. CLAUDE.md is not loaded for it. |
| Hooks | `hooks/hooks.json` | SessionStart: briefs the session on the project's Python toolchain. PreToolUse (Bash): adds a note when a command runs plain `python`/`python3`, suggesting `uv run python`. Never blocks. |
| CLI `pythonista inspect` | `src/python_harness/`, shim `bin/pythonista` | `survey \| gate \| surface \| facts \| calls \| cite`: facts as JSON, never verdicts. |
| CLI `pythonista hooks` | `src/python_harness/hooks/` | `session-start \| guard-python`: the hook handlers, event JSON on stdin and hook JSON on stdout. |

## Requirements

- Claude Code, with `uv` on `PATH` and a POSIX shell (Linux, macOS, WSL). Native Windows is not supported by the shims.
- The CLI needs Python 3.14; `uv` fetches it when it is missing.

## Load it

```sh
claude --plugin-dir ./pythonista          # load it for one session while developing
claude plugin validate --strict ./pythonista
```

To install it for good, list the directory in a plugin marketplace and install it from there (see the Claude Code plugin docs). Hooks and agents are read when a session starts, so start a new session after changing them.

- Claude Code puts the plugin's `bin/` on the Bash tool's `PATH`, after your own entries, so the model can run `pythonista` as a bare command. claude.ai and Cowork refuse to install a plugin that has a top-level `bin/` directory, so this plugin is for Claude Code only.
- Plugin agents cannot be hidden, so `pythonista:pylens` appears in `@` completion. Its description tells Claude not to delegate other work to it.
- pylens runs on Haiku. If many of its citations fail the skill's `inspect cite` check, set `model: sonnet` in `agents/pylens.md`.

## Hooks

Both hooks run `bin/pythonista hooks <event>`. In `hooks` mode the shim turns any failure, its own or the CLI's, into exit code 1. Claude Code reads exit code 2 from a PreToolUse hook as "block this call", and `uv` itself exits 2 on errors. With this mapping, a broken hook shows a hook-error notice and the session or the Bash call goes on.

### SessionStart: the toolchain briefing

On every session start, resume, `/clear` and compaction, the hook adds a short Markdown briefing to Claude's context. It covers:

- the project root;
- the dependency files (`uv.lock`, `poetry.lock`, `pdm.lock`, `pixi.lock`, `Pipfile.lock`, `requirements.txt`);
- the Python pin (`.python-version`), `requires-python`, and the `.venv` interpreter, plus whether it runs a different minor version than the pin;
- ruff: the config file, its `extend` chain (with `${VAR}` expanded) and the effective settings. Rule selection is layered the way ruff layers it: a child `select` starts over, and a child `extend-select` re-enables the parent's ignored codes it covers. A parent ignore broader than the child's selector is still listed as written;
- ty: its config and settings;
- the test suite: the pytest config file by pytest's own precedence, plugins (`pytest-*`, `hypothesis`, `coverage`), tox or nox, and the test directories;
- the declared tools' commands, as `uv run <tool>` (PEP 621, PEP 735, uv and Poetry dependency tables are read);
- the `uv run python` rule.

The search boundary is the nearest directory holding `.git` (or else a `pyproject.toml`) at or above the session's directory. The project root is the nearest `pyproject.toml` inside that boundary. Tool configs and the pin are searched from the root up to the boundary, nearest first. The lock, the dependency files and `.venv` are searched only up to the uv workspace root, and only when `[tool.uv.workspace]` there lists the project as a member and does not exclude it. So a member sees the workspace's lock and `.venv`, and a standalone project nested in a uv repository does not. Nothing above the boundary is read. User-level configs such as `~/.config/ruff/ruff.toml` are not read either, so a missing project config reads "no project config found" rather than "defaults".

The scan only reads files: no subprocess, no network, nothing written. A file that cannot be read becomes a "problem" line instead of a failure. Every value and path read from the repository appears in a code span, with whitespace collapsed and a cap of 240 characters, so repository text cannot start a line of its own. The whole briefing is capped at 9,000 characters; Claude Code's limit is 10,000.

### PreToolUse: the interpreter note

When a Bash command runs `python`, `python3`, `python3.X`, `python3.Xt` or `python2` by bare name, the hook returns `additionalContext` and no permission decision. Per the hooks reference, Claude reads that note next to the tool result, and your permission rules and prompts apply as usual. The command is never blocked. The note says the result may be incorrect, because plain python can pick a different interpreter or packages than the project environment, and lists each call with its `uv run python` rewrite:

```text
Note from the pythonista plugin: this command ran plain `python3`, which can pick a different interpreter or packages than the project environment, so its result may be incorrect. Run Python with `uv run python`, and rerun it that way if the result matters:
- `python3 -m pytest` -> `uv run python -m pytest`
```

The command is parsed with tree-sitter-bash, so a bare name counts anywhere it is the command word: lists and pipelines, subshells, `$(...)`, backticks, and the bodies of conditionals, loops and functions. Up to 10 calls are listed.

- **Bare names only.** `/usr/bin/python3`, `.venv/bin/python`, `sudo python3`, `env python3` and `bash -c "python3 ..."` get no note. Neither do `uv run python`, `which python3` or `command -v python`.
- **Always `uv run python`.** The rewrite drops a version suffix (`python3.14t x` becomes `uv run python x`). It is the same in a Poetry, PDM or Pipenv project, where `uv run` can create its own `uv.lock` and `.venv` (inferred from uv's project behavior, not tested here).
- **Heredocs.** tree-sitter puts the `-` of `python3 - <<EOF` inside the heredoc, so that call is listed as `python3` -> `uv run python`.
- **The `if: "Bash(*python*)"` filter.** It keeps the hook from even starting for Bash commands that do not mention python. A warm run costs about 120 ms. The first run in a fresh install syncs the CLI's venv; the SessionStart hook (300 s timeout) usually does that first.

Try it by hand:

```sh
printf '%s' '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"python3 -m pytest"}}' \
  | bin/pythonista hooks guard-python
printf '%s' "{\"hook_event_name\":\"SessionStart\",\"cwd\":\"$PWD\"}" | bin/pythonista hooks session-start
```

## The shim

`bin/pythonista` is a POSIX `sh` script. It finds the plugin from its own path (`bin/..`), so `UV_PROJECT` is always the plugin no matter where it is called from, and it runs the CLI with `uv run` against that project, without dev dependencies (`UV_NO_DEV`), from the shipped `uv.lock` (`UV_FROZEN`). Its virtualenv lives at `${XDG_CACHE_HOME:-~/.cache}/pythonista/venv-<hash of the plugin path>`, and bytecode goes to `${XDG_CACHE_HOME:-~/.cache}/pythonista/pycache` (`PYTHONPYCACHEPREFIX`). Nothing is written into the installed plugin, and each start stays fast. A plugin update gets a new path and so a new venv; delete `~/.cache/pythonista` to reclaim old ones.

Before running anything it checks its prerequisites and stops with a `pythonista: ...` message on stderr naming the fix:

| Check | Message points to |
| --- | --- |
| `uv` on `PATH` | uv's install page, then a new session |
| `pyproject.toml` and `uv.lock` in the plugin | reinstalling the plugin |
| `XDG_CACHE_HOME` or `HOME` set | a place to keep the venv |
| first-run `uv sync` succeeds | `uv self update`, PyPI access and the Python 3.14 download (uv's own error is printed above it) |

A failed check exits 2 for CLI commands and 1 in `hooks` mode. Outside `hooks` mode the shim `exec`s `uv run`, so the CLI's own exit codes pass through.

`inspect gate` strips those variables (and the shim's virtualenv from `PATH`) before running the reviewed project's tools. It runs them through `uv run --isolated` with caches and bytecode writing turned off, so the gate leaves no lockfile, `.venv` or cache behind. Some build backends still write into the tree (setuptools writes `*.egg-info`). The gate reports any path that appeared in `created_paths` and never deletes anything.

Command groups load only when they run, so the interpreter hook never imports the docs group's HTTP and HTML stack or the session scan.

## Develop

```sh
uv sync
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
claude plugin validate --strict .
```

`ruff.toml` extends Ryan's standing config (`skills/what-would-ryan-say/assets/ruff.toml`, which is also the gate's fallback). It adds the test `S101` exemption and the eval-fixture excludes, and it sets `src` again, because ruff resolves `src` relative to the file that declares it. With the plugin loaded, the interpreter note fires on your own Bash calls here too: run Python as `uv run python`.

## Evaluate the skill

The eval suite lives in `evals/`: eight cases in Claude Code's `claude plugin eval` format. Each case's scaffold builds its fixture git repository and installs the pinned CPython into the run's temporary home, so `--scaffold` is required:

```sh
claude plugin eval . --scaffold \
  --allow-tools Bash Write Edit "WebFetch(domain:pypi.org)" "WebFetch(domain:files.pythonhosted.org)" \
  --judge-model sonnet
```

Add `--model <id>` to pin the agent model, and add `--trust-plugin --no-publish --json results.json` in CI. Linux needs `bubblewrap` and `socat`. `evals/README.md` covers the network and Python requirements, how the old criteria map to graders, and what is still unverified. The suite has not been run yet: eval runs need an authenticated Claude Code.
