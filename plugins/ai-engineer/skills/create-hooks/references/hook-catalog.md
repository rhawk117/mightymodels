# Hook catalog: repository signal to candidate hook

In infer mode, every proposal quotes its signal; a pattern whose signal is absent from the repository is off the table. In describe mode, use it to name the shape a described hook should take and to spot the anti-patterns. Event names and fields are in `hook-facts.md`.

## Contents

- Prevent a failure mode
- Recover from a failure mode
- Inject context
- Track or collect
- Complements to git hooks and CI
- Anti-patterns, do not propose

## Prevent a failure mode (intent: failure mode, before it happens)

| pattern                               | signal                                                                                                                                                                                              | event and shape                                                                                                                                                                                   | posture      |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| command rewrite to the project runner | repo runs tools through `uv`, `poetry`, `pnpm`, `make`, but agents run bare `pytest`, `ruff`, `tsc`                                                                                                 | `PreToolUse`, matcher `Bash`; if the command starts with a bare tool and the project marker exists, return `permissionDecision: allow` with `updatedInput` carrying the wrapped command. Rewrite, do not deny | enforce, 5 s |
| argument-dependent guard              | a command class is dangerous only with certain arguments or against certain targets (`terraform destroy` on a shared workspace, db verbs against non-local hosts, force-push to the default branch, `curl` piped to `sh`) | `PreToolUse`, matcher `Bash`; deny with a reason naming the escalation path. Static patterns with no argument logic go to `permissions.deny` in settings instead                               | enforce, 5 s |
| protected paths with repo logic       | edits to release workflows, lockfiles, migrations, IaC dirs, except when the change came through a documented path                                                                                  | `PreToolUse`, matcher `Edit\|Write`; `tool_input.file_path` is absolute. Deny or ask, narrow set                                                                                                  | enforce, 5 s |

## Recover from a failure mode (intent: failure mode, after it happens)

| pattern                    | signal                                                                                                                               | event and shape                                                                                                                                                                         | posture                           |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| failure playbook           | predictable failures with known fixes: missing venv (`uv sync`), stale deps (`npm install`), migrations behind, missing tool on PATH | `PostToolUseFailure`; match the `error` text (Bash failures start `Exit code N`), return `additionalContext` with the exact fix command and one sentence of why                         | context, exit 0 silently on error |
| test gate before done      | CI runs lint, typecheck or tests                                                                                                     | `Stop`; run the same commands CI runs (fast subset), block once with the failing output as `reason`, allow when `stop_hook_active` is true                                              | gate: allow on internal error     |
| CI mirror at task completion | CI runs lint, tests, or both, and the repo uses agent task lists                                                                   | `TaskCompleted`; run the CI commands and exit 2 with the failing output on stderr, which keeps the task open                                                                            | gate: allow on internal error     |
| format after edit          | CI or pre-commit runs a formatter                                                                                                    | `PostToolUse`, matcher `Edit\|Write`; read `tool_input.file_path`, run the formatter on that file, optionally note it in `additionalContext`; never use `updatedToolOutput` to "fix" content | context, exit 0 silently on error |
| format once per batch      | the formatter is slow, and Claude edits several files in one parallel batch                                                          | `PostToolBatch` (no matcher); read `tool_calls` (each has `tool_name` and `tool_input`), run the formatter once over the edited `file_path` values, before the next model call. Exit 2 or `decision: block` stops the loop, so end with exit 0                      | context, exit 0 silently on error |
| format on external edits   | files are changed outside Claude Code (an editor, a generator) and the formatter or a reload should follow                           | `FileChanged`, matcher the literal file names to watch (`.envrc\|.env`); reads the absolute `file_path` and `event` (`change`, `add`, `unlink`); side effects only, no decision control, and the action must be idempotent or its own change re-fires the hook; `CLAUDE_ENV_FILE` persists variables for later Bash commands           | tracking, exit 0 silently on error |
| rewrite a command          | agents habitually run a command that needs a flag or wrapper                                                                         | `PreToolUse` returns `permissionDecision: allow` with `updatedInput` (the whole input object, unchanged fields included)                                                                | enforce, 5 s                      |

## Inject context (intent: context)

| pattern             | signal                                                                                                             | event and shape                                                                                                                         | posture |
| ------------------- | ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| session orientation | facts an agent cannot read from static files: dirty tree, ahead/behind, canonical build/test commands, repo skills | `SessionStart`; compute at fire time, return `additionalContext` of about ten lines of factual statements                               | context |
| per-agent charter   | custom agents under `.claude/agents/`, `~/.claude/agents/` or a plugin                                             | `SubagentStart`, matcher on the agent type; `additionalContext` with scope and report format                                            | context |
| output truncation   | chatty tooling and long sessions                                                                                   | `PostToolUse`, matcher `Bash`; if `tool_response.stdout` is huge, return `updatedToolOutput` with the full `Bash` output shape (`stdout`, `stderr`, `interrupted`, `isImage`) trimmed to head and tail | context |

Static prose is not a hook: a `SessionStart` hook that injects fixed text is an instructions file with a process launch attached. For instructions that never change, prefer `CLAUDE.md`.

## Track or collect (intent: tracking)

| pattern        | signal                                                         | event and shape                                                                                                                                                  | posture                            |
| -------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| audit log      | compliance need or a request for visibility                    | `UserPromptSubmit` + `PreToolUse` (+ `SessionStart`/`SessionEnd`); append redacted JSONL to a gitignored path; add the path to `.gitignore` in the same change | tracking, exit 0 silently on error |
| telemetry      | metrics on tool mix, durations, failures                       | `PostToolUse` + `PostToolUseFailure`; JSONL; never on stdout                                                                                                     | tracking                           |
| slow tracking  | the tracking or sync step takes seconds and Claude need not wait | the same events with `"async": true` on the handler: it runs in the background and cannot block. `asyncRewake: true` wakes Claude on exit 2 for a long check that should interrupt only on failure | tracking                           |

## Complements to git hooks and CI (keep the hook, name what it complements)

| pattern                        | complements               | shape                                                                                              |
| ------------------------------ | ------------------------- | -------------------------------------------------------------------------------------------------- |
| run pre-commit after each edit | `.pre-commit-config.yaml` | `PostToolUse` on `Edit\|Write` running `pre-commit run --files PATH`; the agent never has to remember |
| CI mirror at turn end          | workflow lint/test steps  | the test gate above, running CI's exact commands                                                   |

## Subagent reports

| pattern             | signal                                                  | event and shape                                                                                                                                                         |
| ------------------- | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| subagent report gate | custom agents expected to return structured reports    | `SubagentStop` validating `last_assistant_message`; block once with the schema as `reason`. `SubagentStop` carries `stop_hook_active`, so guard it the way `Stop` is guarded |

Hard restrictions for a subagent belong in its agent file's tool list; this gate is quality control, not a security boundary.

## Anti-patterns, do not propose

- Events that do not exist (`PreCommit`, `OnFileSave`, a camelCase `preToolUse`).
- Automation that needs an interactive answer: a `PreToolUse` `ask` is unanswerable under `claude -p`; headless policy lands on `allow` or `deny`.
- A deny-everything posture via hooks alone: a timed-out `PreToolUse` command hook does not block, and exit 1 without JSON proceeds. Enforcement needs exit 2 or a printed deny, and hooks complement permissions and agent definitions rather than replace them.
- Slow enforcement hooks: a two-second check on every tool call is what gets the whole hook layer disabled.
- Large context blobs at `SessionStart`: paid on every session, and capped at 10,000 characters.
- A deny hook for a static blocklist that a `permissions.deny` rule already expresses.
- Repository duplicates of guards already at user or managed level: both fire, twice the latency, no extra coverage. An identical handler in several settings files runs once, but a plugin's copy stays separate.
