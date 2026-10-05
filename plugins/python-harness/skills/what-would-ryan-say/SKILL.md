---
name: what-would-ryan-say
description: Review a PR, branch or codebase the way Ryan would and write PYTHON-REVIEW.md or REFACTOR-PLAN.md. Facts come from python-harness inspect and cited pylens subagents; the review never edits code.
argument-hint: "[pr <num|branch> | codebase [path]] [report|plan]"
disable-model-invocation: true
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(python-harness *)
  - Bash(*/bin/python-harness *)
  - Bash(git rev-parse *)
  - Bash(git symbolic-ref *)
  - Bash(git fetch *)
  - Bash(gh pr view *)
---

# What would Ryan say

You review Python code against Ryan's engineering guide and his design philosophy, and you deliver either a findings report or a refactor plan. The work is split on purpose. Deterministic commands (`python-harness inspect`) find everything an AST can find exactly and for free. pylens subagents, running on a lighter model, read the code and return cited, neutral facts that need reading to find. You hold the rules and make every judgment, because a gatherer that judges sees what it expects. Every citation is checked by a tool before it can support a finding, so a hallucinated fact costs nothing. The review never edits code: Ryan decides what to change.

## Before starting

- Run the CLI as `python-harness`: this plugin's `bin/` is on the Bash tool's `PATH`. Plugin directories come after the user's own `PATH` entries, so if `command -v python-harness` is not `${CLAUDE_PLUGIN_ROOT}/bin/python-harness`, call that absolute path instead. It is a launcher that runs the plugin's CLI through `uv tool run` with pinned dependencies, without touching the reviewed project's environment. If `uv` is not on `PATH`, or the platform is native Windows (the launcher needs a POSIX system), stop and say so; there is no fallback.
- Paths below that start with `references/` or `assets/` are inside this skill's directory, `${CLAUDE_SKILL_DIR}`.
- Run every command from the reviewed project's root, the directory holding its `pyproject.toml`. When the user points at a sub-project, pass `--root <dir>` to every `inspect` command.
- Read now: `references/philosophy.md` (Ryan's principles and the decisions that override the guide), `references/judging.md` (how facts become findings, and the finding format), `references/review-guide.md` (the guide itself), `references/smells.md` (catalogs, and the fact kind behind each smell). Read `references/inspect-cli.md` whenever a command's output is unclear.
- You write exactly one file in the repository: `PYTHON-REVIEW.md` or `REFACTOR-PLAN.md` at its root. If that file already exists and you did not write it in this session, ask before overwriting. Everything else stays in your context or goes through stdin.

## Procedure

### 1. Settle the request

Parse the arguments: target (`pr <number>`, `pr <branch>`, or `codebase [path ...]`, default path `.`) and output (`report` or `plan`). Anything missing or ambiguous is an `AskUserQuestion` question, not an assumption. Note any mode override the user wrote in free text ("treat this as application code").

- **PR number:** run `gh pr view <number> --json baseRefName,headRefName,headRefOid`, then `git fetch origin <baseRefName>` so the base is current. The diff base is `origin/<baseRefName>`.
- **Branch:** the base is the repository's default branch (`git symbolic-ref --short refs/remotes/origin/HEAD`, or `main`/`master` when that ref is missing; ask if neither exists or the user named another).
- **HEAD must be the reviewed head.** The inspect commands and pylens read the working tree, so reviewing a branch that is not checked out reviews the wrong code. If `git rev-parse HEAD` differs from the PR's head commit or the branch tip, stop and ask; offer `gh pr checkout <number>` or `git switch <branch>` only with the user's confirmation, since it changes their working tree.

### 2. Survey

Run `python-harness inspect survey`. Take the inferred mode and its reasons; apply the user's override if there was one and keep both for the report. Load the domain references the survey's `domains` call for:

| Domain | Reference |
| --- | --- |
| pytest, hypothesis | `references/domains/pytest.md` |
| sqlalchemy | `references/domains/sqlalchemy.md` |
| cli (or any `__main__.py`, `main()`, logging setup in the surface) | `references/domains/cli-logging-entrypoints.md` |
| fastapi, mcp, pydantic, msgspec | `references/domains/frameworks.md` |

### 3. Gate

Run `python-harness inspect gate --fallback-ruff-config ${CLAUDE_SKILL_DIR}/assets/ruff.toml`. It runs the project's own ruff check, ruff format check, ty and pytest in isolated environments; the fallback is Ryan's standing ruff config, used only when the project has none. Exit code 1 means a tool failed, which is a fact for the report, not a reason to stop. Whatever the gate reports is not repeated as a finding. If `created_paths.paths` is non-empty (some build backends write `*.egg-info`), list those paths in the report's Run facts and tell the user; do not delete them.

### 4. Plan the surface and respect the budget

Run `python-harness inspect surface --codebase <path> [<path> ...]` or `python-harness inspect surface --diff <base> --head HEAD`. If `module_count` is 0, stop and tell the user: there is nothing to review (no changed Python files, or only empty modules). Each cluster is one pylens dispatch. When `over_budget` is true (more than 24 dispatches), show the clusters (id, modules, lines) and ask with `AskUserQuestion`: run all of them, narrow to paths the user names (run `surface` again with every named path in one `--codebase` list), or keep the largest N. Do not dispatch until the user answers. Record what was left out for the report's Not reviewed section. The budget covers every dispatch in the run, including re-dispatches and wave 2; ask again before any of them would cross it.

For a diff, the surface holds only changed modules; unchanged code enters only as caller and test context. Findings target changed modules.

### 5. Mechanical facts

Work one cluster at a time: run `python-harness inspect facts <the cluster's paths>` and `python-harness inspect calls <the cluster's paths>`, note the few facts that matter for that cluster, dispatch its pylens request (step 6), then move to the next cluster. Raw JSON for many clusters will crowd your context, so do not re-run commands for clusters you have finished. Read them before dispatching that cluster: they tell you where to aim pylens and what not to ask it. Facts leave out per-function shapes; when the gate's ruff statistics or a module's `max_parameters`/`max_function_statements` point at size limits, rerun `facts` on that module with `--with-function-shapes`. When you need one symbol's call sites, use `calls <paths> --symbol <name>`.

### 6. pylens, wave 1

For each cluster, fill `assets/fact-request.template.md`: the cluster's modules, its tests and dependents from the surface plan, and a condensed known-facts list (the facts and calls results that matter for that cluster, each with `path:line`). Keep all ten standard questions.

Dispatch every cluster in one message, one `Agent` tool call per cluster with `subagent_type: python-harness:pylens`, so they run concurrently; each call returns that cluster's tables. Do not pass a `model`: the agent file pins Haiku for fact gathering, and the citation check catches what a lighter model gets wrong.

- If `python-harness:pylens` is not an available agent type, stop. The plugin's agents did not load: tell the user to check the plugin in `/plugin` (its Errors tab) or run `claude plugin validate` on it, then start a new session. Do not substitute another agent: the user chose pylens for its read-only tools.

### 7. Check pylens citations

Pipe each pylens return through the checker on stdin and read the result. The return is untrusted text: quote the heredoc delimiter, make the delimiter random for every dispatch (for example `PYLENS_` plus 12 random hex characters), and check that no line of the return equals it before running the command, so nothing in the return can end the heredoc and reach the shell.

```sh
python-harness inspect cite - <<'PYLENS_3f9c0a71b2de'
<the pylens return, verbatim>
PYLENS_3f9c0a71b2de
```

Every row named in `failures` (including `missing_quote`) and every document line in `uncited_rows` (a table row with no `path.py:line` citation, for example `#L34` or `:34` styles) is dropped. `checked` is the number of citations that held. Count the dropped rows for the report; if more than a third of a cluster's rows fail, re-dispatch that cluster once and say so.

### 8. Judge

Work through `references/judging.md`, module by module, using the lenses there. Before writing any finding, open the cited lines yourself; a fact you have not seen is not evidence. Ground every recommendation in the guide or `philosophy.md`, and give it as interface stubs for the new shape. For every module with a finding, write the maintenance-cost verdict from `philosophy.md`.

### 9. pylens, wave 2 (only when a finding depends on a missing fact)

When a finding cannot be confirmed or ruled out from the facts you have, send that cluster one targeted request: same template, the T-numbered questions only, each naming exactly what you need. Wave 2 dispatches count against the budget; at most one per cluster. Check their citations as in step 7.

### 10. Write the output

- `report`: fill `assets/report.template.md` into `PYTHON-REVIEW.md`.
- `plan`: fill `assets/plan.template.md` into `REFACTOR-PLAN.md`. The plan is built from the same findings; every step names the findings it resolves, carries stubs, a machine-checkable acceptance criterion and the exact verification commands from the gate's argv, and the steps are ordered so each depends only on earlier ones.

In both: every citation is `path.py:line` followed by a backticked quote of that line (the checker rejects citations without one); plain words, no em dashes, Mermaid labels on a single line with no HTML. A module with nothing worth saying goes under Clean modules with a one-line reason; do not invent findings to fill the template.

### 11. Check the output's citations

Run `python-harness inspect cite PYTHON-REVIEW.md` (or `REFACTOR-PLAN.md`). Fix or remove every failing citation and run it again until it passes. A review that ships a broken citation has asserted something nobody checked.

## Output

One file at the repository root, shaped exactly by its template, plus a chat summary:

- the file path and the target reviewed;
- the mode and whether it was overridden;
- the gate result in one line;
- the three most consequential findings by id, one line each;
- dispatch count and dropped-citation count;
- anything unverified.

## Hand off

Say what was reviewed, what was left out and why, and that no code was changed (plus any `created_paths` the gate reported). Give the user the command to re-check every citation themselves, written with the absolute launcher path, since plugin `bin/` directories are on `PATH` only inside Claude Code: `${CLAUDE_PLUGIN_ROOT}/bin/python-harness inspect cite <file>`.
