# python-harness

A Claude Code plugin for Python engineering. It ships:

| Component | Path | What it does |
| --- | --- | --- |
| Skill `what-would-ryan-say` | `skills/what-would-ryan-say/` | `/python-harness:what-would-ryan-say pr <num\|branch> \| codebase [path]  report \| plan`: reviews Python against Ryan's guide and philosophy, writes `PYTHON-REVIEW.md` or `REFACTOR-PLAN.md`, never edits code. Runs only when you type it. |
| Agent `pylens` | `agents/pylens.md` | Read-only fact gatherer (`Read`, `Grep`, `Glob`) on Haiku, dispatched by the skill as `python-harness:pylens`. CLAUDE.md is not loaded for it. |
| Hooks | `hooks/hooks.json` | SessionStart: briefs the session on the project's Python toolchain. PreToolUse (Bash): adds a note when a command runs plain `python`/`python3`, suggesting `uv run python`. Never blocks. |
| CLI `python-harness inspect` | `src/python_harness/`, launcher `bin/python-harness` | `survey \| gate \| surface \| facts \| calls \| cite`: facts as JSON, never verdicts. |
| CLI `python-harness hooks` | `src/python_harness/hooks/` | `session-start \| guard-python`: the hook handlers, event JSON on stdin and hook JSON on stdout. |

## Requirements

- Claude Code, with `uv` on `PATH`, on a POSIX system (Linux, macOS, WSL). The launcher does not run on native Windows.
- The CLI needs Python 3.14; `uv` fetches it when it is missing.

## Load it

```sh
claude --plugin-dir ./python-harness      # load it for one session while developing
claude plugin validate --strict ./python-harness
```

To install it for good, list the directory in a plugin marketplace and install it from there (see the Claude Code plugin docs). Hooks and agents are read when a session starts, so start a new session after changing them.

- Claude Code puts the plugin's `bin/` on the Bash tool's `PATH`, after your own entries, so the model can run `python-harness` as a bare command. claude.ai and Cowork refuse to install a plugin that has a top-level `bin/` directory, so this plugin is for Claude Code only.
- Plugin agents cannot be hidden, so `python-harness:pylens` appears in `@` completion. Its description tells Claude not to delegate other work to it.
- pylens runs on Haiku. If many of its citations fail the skill's `inspect cite` check, set `model: sonnet` in `agents/pylens.md`.

## Hooks

Both hooks run `bin/python-harness hooks <event> || exit 1`, so Claude Code only ever gets exit code 0 or 1 from them. On exit 1 it shows a hook-error notice and the session or the Bash call goes on. That covers a payload a handler cannot read, a usage error, and a failure before the CLI starts: `uv` missing from `PATH` (127 from `env`), or `uv` unable to build the environment. The `|| exit 1` is there for that last case. Claude Code reads exit code 2 from a PreToolUse hook as "block this call", `uv` exits 2 for some of its own errors, such as finding no Python 3.14 while downloads are turned off, and the launcher itself maps no exit codes. `tests/plugin/test_launcher.py` runs both commands from `hooks/hooks.json` against a failing `uv` and fails if any other code comes out.

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
Note from the python-harness plugin: this command ran plain `python3`, which can pick a different interpreter or packages than the project environment, so its result may be incorrect. Run Python with `uv run python`, and rerun it that way if the result matters:
- `python3 -m pytest` -> `uv run python -m pytest`
```

The command is parsed with tree-sitter-bash, so a bare name counts anywhere it is the command word: lists and pipelines, subshells, `$(...)`, backticks, and the bodies of conditionals, loops and functions. Up to 10 calls are listed.

- **Bare names only.** `/usr/bin/python3`, `.venv/bin/python`, `sudo python3`, `env python3` and `bash -c "python3 ..."` get no note. Neither do `uv run python`, `which python3` or `command -v python`.
- **Always `uv run python`.** The rewrite drops a version suffix (`python3.14t x` becomes `uv run python x`). It is the same in a Poetry, PDM or Pipenv project, where `uv run` can create its own `uv.lock` and `.venv` (inferred from uv's project behavior, not tested here).
- **Heredocs.** tree-sitter puts the `-` of `python3 - <<EOF` inside the heredoc, so that call is listed as `python3` -> `uv run python`.
- **The `if: "Bash(*python*)"` filter.** It keeps the hook from even starting for Bash commands that do not mention python. A warm run costs about 150 ms. On the first run `uv` builds the launcher's environment; the SessionStart hook (300 s timeout) usually does that first.

Try it by hand:

```sh
printf '%s' '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"python3 -m pytest"}}' \
  | bin/python-harness hooks guard-python
printf '%s' "{\"hook_event_name\":\"SessionStart\",\"cwd\":\"$PWD\"}" | bin/python-harness hooks session-start
```

## The launcher

`bin/python-harness` is a Python script. Its first line runs it through `uv tool run`, with the Python version and one `--with name==version` per runtime dependency pinned on that line. It uses `uv tool run` and not `uv run`, because `uv run` adopts the `.venv`, `pyproject.toml` and `uv.toml` of the directory it is called from, and that directory is the project under review. The script finds the plugin from its own path (`bin/..`), puts the plugin's `src` on `sys.path` and calls the CLI, so the CLI's exit codes pass through. `uv` builds the environment in its own cache on the first run and reuses it afterwards. Python caches bytecode in `__pycache__` directories beside the plugin's sources.

The pins select versions and do not verify hashes. `tests/plugin/test_launcher.py` compares them with `pyproject.toml` and the repository's `uv.lock`, and fails when they differ.

Nothing is checked before the CLI starts:

| Problem | What you see |
| --- | --- |
| `uv` is not on `PATH` | `env` prints `'uv': No such file or directory` and exits 127 |
| `uv` cannot build the environment (no network on the first run, no Python 3.14) | `uv`'s own error and exit code |

`uv tool run` puts its environment's `bin` first on `PATH` and sets `UV`. `inspect gate` removes both, and an inherited `VIRTUAL_ENV` with that virtualenv's `bin`, before running the reviewed project's tools. It runs them through `uv run --isolated` with caches and bytecode writing turned off, so the gate leaves no lockfile, `.venv` or cache behind. Some build backends still write into the tree (setuptools writes `*.egg-info`). The gate reports any path that appeared in `created_paths` and never deletes anything.

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
