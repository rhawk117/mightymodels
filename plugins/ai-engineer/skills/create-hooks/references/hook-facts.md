# Claude Code hook facts this skill depends on

Snapshot of the Claude Code hooks reference and hooks guide taken 2026-10-03. A behavior outside this file is unverified: say so to the user instead of asserting it. Event names are PascalCase (`PreToolUse`), and a name outside the list below silently never fires.

## Contents

- Where hooks live and which one wins
- Config shape and handler fields
- Matchers
- Events
- Input payload
- Output contract: exit codes, stdout, JSON
- Decision shapes per event
- Environment variables
- Gotchas

## Where hooks live and which one wins

| Location                                | Scope                                         | Shareable                 |
| --------------------------------------- | --------------------------------------------- | ------------------------- |
| `~/.claude/settings.json`               | all your projects                             | no, local to your machine |
| `.claude/settings.json`                 | one project                                   | yes, commit it            |
| `.claude/settings.local.json`           | one project, personal                         | no, gitignored            |
| managed policy settings                 | organization-wide                             | yes, admin-controlled     |
| plugin `hooks/hooks.json`               | while the plugin is enabled                   | yes, ships with the plugin |
| skill or subagent frontmatter           | while the skill was invoked or the subagent runs | yes, in the component file |

- Each settings file carries its hooks under one `hooks` key; there is no directory of one file per concern. A plugin puts them in `hooks/hooks.json` at the plugin root or in the `hooks` key of `plugin.json`; both load. A plugin hooks file holds only `hooks` and an optional `description`; a settings file also holds other keys.
- Hook entries merge across levels instead of replacing each other. All matching hooks run in parallel. A handler defined identically in several settings files runs once; a plugin's or a skill's copy of the same handler stays separate and runs too.
- Settings, managed and plugin hooks also run inside subagents: tool events fire the same hooks, and the payload carries `agent_id` and `agent_type`.
- Claude Code fires the same events in the terminal, IDE extensions, the Desktop app and cloud sessions. Cloud sessions do not read `~/.claude/settings.json`.
- Administrators can set `allowManagedHooksOnly` in managed settings: user, project, local and plugin hooks are then blocked, except plugins force-enabled by managed `enabledPlugins`.
- `"disableAllHooks": true` in a settings file turns off every hook the user controls, and a `false` in a project file overrides a `true` in user settings. There is no way to disable one hook and keep it configured. Managed hooks stay unless the setting is at the managed level.
- Direct edits to hooks in settings files are normally picked up by a file watcher while Claude Code runs. `/hooks` opens a read-only browser that labels each hook with its source. A hook that still does not fire after an edit: restart the session, then read the debug log (unverified: the docs name the watcher, not a restart, as the fallback).
- Workspace trust: in an interactive session Claude Code holds back hooks from every settings file, your own `~/.claude/settings.json` included, until the folder's trust dialog is accepted. A `-p` or SDK session never shows the dialog and treats the folder as trusted, so hooks committed to `.claude/settings.json` run there on first contact.

## Config shape and handler fields

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python3", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/guard.py"], "timeout": 5}]}]}}
```

Three levels: the event, a matcher group (`matcher`, and a `hooks` array), and the handlers in that array. There is no `version` key. The handler types are `command`, `http`, `mcp_tool`, `prompt` and `agent`; this skill builds `command` hooks and, for telemetry only, `http`.

Fields on every handler:

| Field           | Meaning                                                                                                                                  |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `type`          | required                                                                                                                                 |
| `if`            | one permission rule such as `Bash(git *)` or `Edit(*.ts)`; the process starts only on a match. Evaluated on tool events only; on any other event a hook with `if` never runs. Best-effort: when Claude Code cannot tell what a Bash input runs, the hook runs anyway |
| `timeout`       | seconds. Defaults: 600 for `command`, `http` and `mcp_tool`; 30 for `prompt`; 60 for `agent`. Lowered to 30 on `UserPromptSubmit` and the model-switch events, 10 on `MessageDisplay`. `SessionEnd` hooks share a 1.5 second budget, raised to a longer per-hook `timeout` up to 60 seconds |
| `statusMessage` | spinner text                                                                                                                             |
| `once`          | only honored for hooks declared in skill frontmatter                                                                                     |

Command handler fields:

| Field         | Meaning                                                                                                                       |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `command`     | required; the shell command, or with `args` the executable to spawn                                                           |
| `args`        | argument list; its presence selects exec form: no shell, each element is one argument, placeholders are substituted as plain strings |
| `shell`       | `bash` or `powershell`; ignored when `args` is set                                                                            |
| `async`       | run in the background; cannot block or decide, and `timeout` is not enforced on it                                            |
| `asyncRewake` | background run that wakes Claude on exit 2, with stderr (or stdout when stderr is empty) shown as a system reminder; `timeout` is still enforced |

Without `args` the command runs as shell form (`sh -c`, Git Bash on Windows, or PowerShell when Git Bash is missing). Prefer exec form for any command that names a path placeholder; in shell form wrap each placeholder in double quotes. A Python script needs no per-platform pair: one handler runs it everywhere that has the interpreter on `PATH`.

`http` handlers take `url`, `headers` and `allowedEnvVars` (only listed variables are interpolated into header values). A 2xx response with a JSON body is read like command stdout; any other status, a connection failure or a plain-text body is a non-blocking error, so an HTTP hook blocks only through the JSON body. The `allowedHttpHookUrls` setting restricts which URLs may run.

Path placeholders, substituted in `command` and `args` and also exported as environment variables:

- `${CLAUDE_PROJECT_DIR}`: the project root where the session started; it stays put when Claude enters a worktree, while `cwd` in the payload follows Claude.
- `${CLAUDE_PLUGIN_ROOT}`: the plugin's installation directory.
- `${CLAUDE_PLUGIN_DATA}`: the plugin's persistent data directory, for state that survives updates.

Handlers run in the current directory; there is no `cwd` field, so address scripts through a placeholder.

## Matchers

A `matcher` goes on the matcher group. How it is read:

| Value                                              | Read as                                                                    |
| -------------------------------------------------- | -------------------------------------------------------------------------- |
| omitted, empty or `*`                              | matches every occurrence                                                   |
| only letters, digits, `_`, `-`, spaces, `,` and `\|` | an exact name, or an exact list separated by `\|` or `,`                  |
| anything else                                      | a JavaScript regular expression, unanchored (`RegExp.prototype.test`)      |

`Edit.*` matches `Edit` and `NotebookEdit`; write `^Edit$` for a whole-string match. `FileChanged` and `StopFailure` use a narrower exact-match set (letters, digits, `_`, `|`). A matcher on an event with no matcher support is silently ignored. What each event matches:

| Event                                                                        | Matches on                                                       |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PermissionRequest`, `PermissionDenied` | tool name: `Bash`, `Edit\|Write`, `mcp__.*`           |
| `SessionStart`                                                               | `startup`, `resume`, `clear`, `compact`, `fork`                  |
| `SessionEnd`                                                                 | exit reason: `clear`, `resume`, `logout`, `prompt_input_exit`, `other` |
| `Notification`                                                               | notification type such as `permission_prompt`, `idle_prompt`     |
| `SubagentStart`, `SubagentStop`                                              | agent type: `general-purpose`, `Explore`, `Plan`, custom names   |
| `PreCompact`, `PostCompact`                                                  | `manual`, `auto`                                                 |
| `StopFailure`                                                                | error type such as `rate_limit`, `server_error`                  |
| `FileChanged`                                                                | literal file names to watch, such as `.envrc\|.env`              |
| `UserPromptSubmit`, `PostToolBatch`, `Stop`, `TaskCreated`, `TaskCompleted`, `CwdChanged` and others | no matcher support                          |

Tool names are PascalCase: `Bash`, `PowerShell`, `Edit`, `Write`, `Read`, `Glob`, `Grep`, `Agent`, `WebFetch`, `WebSearch`, `AskUserQuestion`, `ExitPlanMode`. MCP tools are `mcp__<server>__<tool>`, and `mcp__plugin_<plugin>_<server>__<tool>` for a server a plugin bundles. Matching a whole server needs `.*`: `mcp__memory` alone is an exact string that matches no tool.

## Events

Thirty-three events exist and nothing else fires: `SessionStart`, `Setup`, `UserPromptSubmit`, `UserPromptExpansion`, `PreToolUse`, `PermissionRequest`, `PermissionDenied`, `PostToolUse`, `PostToolUseFailure`, `PostToolBatch`, `Notification`, `MessageDisplay`, `SubagentStart`, `SubagentStop`, `TaskCreated`, `TaskCompleted`, `Stop`, `StopFailure`, `TeammateIdle`, `InstructionsLoaded`, `ConfigChange`, `CwdChanged`, `DirectoryAdded`, `FileChanged`, `WorktreeCreate`, `WorktreeRemove`, `PreCompact`, `PostCompact`, `PreModelSwitch`, `PostModelSwitch`, `Elicitation`, `ElicitationResult`, `SessionEnd`.

The events this skill proposes against, with what each can do:

| Event                | Fires                                                                 | Can block        | Output the host acts on                                                             |
| -------------------- | --------------------------------------------------------------------- | ---------------- | ----------------------------------------------------------------------------------- |
| `SessionStart`       | a session starts or resumes                                           | no               | `additionalContext`; plain stdout is also added as context                          |
| `UserPromptSubmit`   | a prompt is submitted, before Claude processes it                     | yes              | `decision: block` with `reason`, or `additionalContext`; plain stdout is added as context |
| `PreToolUse`         | before a tool call executes                                           | yes              | `permissionDecision`, `permissionDecisionReason`, `updatedInput`, `additionalContext` |
| `PermissionRequest`  | a tool call needs a permission decision                               | by decision only | `decision.behavior` allow or deny                                                   |
| `PostToolUse`        | after a tool call succeeds                                            | no               | `additionalContext`, `updatedToolOutput`, `decision: block` with `reason`           |
| `PostToolUseFailure` | after a tool call fails                                               | no               | `additionalContext`                                                                 |
| `PostToolBatch`      | after a batch of parallel tool calls resolves, before the next model call | yes (stops the loop) | `decision: block`                                                              |
| `Notification`       | Claude Code sends a notification                                      | no               | none                                                                                |
| `SubagentStart`      | a subagent is spawned                                                 | no               | `additionalContext`                                                                 |
| `SubagentStop`       | a subagent finishes                                                   | yes              | `decision: block` with `reason`, or `additionalContext`                             |
| `TaskCompleted`      | a task is being marked completed                                      | yes              | exit 2 keeps the task open                                                          |
| `Stop`               | Claude finishes responding                                            | yes              | `decision: block` with `reason`, or `additionalContext`                             |
| `StopFailure`        | the turn ends on an API error                                         | no               | none; output and exit code are ignored                                              |
| `FileChanged`        | a watched file changes on disk, including changes outside Claude Code | no               | none; side effects only                                                             |
| `PreCompact`         | before context compaction                                             | yes              | exit 2 or `decision: block`                                                         |
| `SessionEnd`         | a session ends                                                        | no               | none; 1.5 second default budget                                                     |

`SessionEnd` takes a matcher on the exit reason, and `SubagentStop` one on the agent type. Hooks cannot block `StopFailure`, `Notification`, `SessionStart`, `SubagentStart`, `SessionEnd` or `PostToolUse`; a `PostToolUse` or `PostToolUseFailure` exit 2 only shows stderr to Claude because the tool already ran.

## Input payload

Every hook receives one JSON object on stdin, snake_case, with the event named in the payload, so one script can serve several events and no `--event` argument is needed:

- Common fields: `session_id`, `transcript_path`, `cwd`, `hook_event_name`, and on most events `permission_mode` (`default`, `plan`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`; the "Manual" mode arrives as `default`). `prompt_id`, `effort` and `scratchpad_dir` appear on some. Inside a subagent, or under `--agent`, `agent_id` and `agent_type` are added. There is no timestamp field.
- `PreToolUse`: `tool_name`, `tool_input`, `tool_use_id`. `tool_input` is an object. For `Write`, `Edit` and `Read`, `tool_input.file_path` is always absolute; `Bash` has `tool_input.command`.
- `PostToolUse`: the same, plus `tool_response`, the result the tool returned. `Bash` returns `stdout`, `stderr`, `interrupted` and `isImage`.
- `PostToolUseFailure`: `tool_name`, `tool_input`, `error` (a string), `is_interrupt`, `duration_ms`. For Bash and PowerShell a command that ran and exited gives `error` a first line `Exit code N`, then its output; a bare message with no exit-code line means the shell could not start. Key on `tool_name`, `is_interrupt` and the `Exit code N` first line, and treat the rest as display text.
- `PermissionRequest`: `tool_name`, `tool_input` and optional `permission_suggestions`, without `tool_use_id`.
- `UserPromptSubmit`: `prompt`.
- `SessionStart`: `source` (`startup`, `resume`, `clear`, `compact`, `fork`) and optionally `model`, `agent_type`, `session_title`.
- `SessionEnd`: `reason`.
- `Stop`: `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons`. `stop_hook_active` is true when Claude Code is already continuing because of a stop hook.
- `SubagentStart`: `agent_id` and `agent_type`. `SubagentStop`: `stop_hook_active`, `agent_id`, `agent_type`, `agent_transcript_path`, `last_assistant_message`.
- `StopFailure`: `error`, optional `error_details`, optional `last_assistant_message`. `Notification`: `message`, optional `title`, `notification_type`. `PreCompact`: `trigger`, `custom_instructions`.

## Output contract

Exit codes first, JSON second. Claude Code reads JSON from stdout on every exit code, but exit 2's block is the one outcome JSON cannot override.

- Exit 0: success. Stdout is parsed as JSON when it starts with `{` and ends with `}`; anything else, a JSON array or a quoted string included, is plain text. Plain text becomes context only on `UserPromptSubmit`, `UserPromptExpansion`, `SessionStart` and `PostModelSwitch`; on other events it goes to the debug log. Stdout that starts with `{` and does not parse, or parses and fails the schema, is a non-blocking error: the action proceeds and the transcript shows a hook error.
- Exit 2: a blocking error on the events that can block (`PreToolUse`, `UserPromptSubmit`, `UserPromptExpansion`, `Stop`, `SubagentStop`, `TaskCompleted`, `TaskCreated`, `PostToolBatch`, `PreCompact`, `ConfigChange` and others). Stderr is the reason Claude reads. `PermissionRequest`, `Notification`, `StopFailure` and `PostToolUse` ignore it or only show stderr; `PermissionRequest` denies through its `decision` object instead.
- Any other exit code is a non-blocking error: the action proceeds. Without valid JSON on stdout, exit 1 does not block even though it is the conventional Unix failure code. A shell-form command whose program is not found exits 127 and also proceeds, so a mistyped command leaves a gate silently off; `python3` given a script path that does not exist exits 2, which blocks instead. An enforcing hook must exit 2 or print a deny.
- Timeouts: a timed-out `command`, `http` or `mcp_tool` hook does not block the tool call; the call continues through the normal permission flow, so a stalled hook is not a gate.
- Stderr from a hook that exits 0 goes to the debug log only, and Claude never sees it.
- Choose one approach per hook: exit codes alone, or exit 0 with JSON.
- Stdout must hold only the JSON object, so a shell profile that prints on startup breaks it.
- Size: `additionalContext`, `systemMessage` and `initialUserMessage` strings, and plain stdout, are capped at 10,000 characters each. Over the cap, Claude Code saves the output to a file in the session directory and passes Claude the path and a preview of the first 2,000 characters; it does not ask Claude to read the file, so keep anything that must always be seen inside the cap.

Universal JSON fields, accepted by every event (some events discard them; the event section in the docs says which):

| Field            | Meaning                                                                   |
| ---------------- | ------------------------------------------------------------------------- |
| `continue`       | `false` stops Claude entirely after the hook; overrides event decisions   |
| `stopReason`     | message shown to the user when `continue` is false                        |
| `systemMessage`  | warning shown to the user                                                 |
| `terminalSequence` | an allow-listed escape sequence, such as a desktop notification, emitted for you; interactive sessions only |

## Decision shapes per event

Event-specific fields go in a `hookSpecificOutput` object that requires `hookEventName` set to the event name. Top-level `decision` and `reason` are used by `UserPromptSubmit`, `PostToolUse`, `PostToolUseFailure`, `PostToolBatch`, `Stop`, `SubagentStop` and `PreCompact`.

- `PreToolUse` returns its decision inside `hookSpecificOutput`: `permissionDecision` is `allow`, `deny`, `ask` or `defer`, with `permissionDecisionReason` (shown to Claude on deny, to the user on ask). `updatedInput` replaces the whole input object, so include unchanged fields; pair it with `allow` to auto-approve or `ask` to show the user the modified input. `additionalContext` is added next to the tool result. With several hooks the precedence is `deny`, then `defer`, `ask`, `allow`. A hook's `allow` does not override deny and ask rules in settings. Top-level `decision` and `reason` on this event are deprecated.
- `PermissionRequest`: `hookSpecificOutput.decision.behavior` is `allow` or `deny`, with `updatedInput` inside the `decision` object when allowing.
- `PostToolUse`: `hookSpecificOutput.updatedToolOutput` replaces what Claude sees and must match the tool's output shape (a mismatch is ignored and the original output used); `additionalContext` adds context; top-level `decision: block` with `reason` adds the reason next to the result. A block does not undo the call: the tool already ran and Claude still sees the original output. Use `PreToolUse` to prevent a call.
- `PostToolUseFailure`, `SubagentStart`, `SessionStart`: `hookSpecificOutput.additionalContext`.
- `UserPromptSubmit`: `additionalContext` injects context alongside the prompt; top-level `decision: block` with `reason` rejects it. The prompt cannot be rewritten.
- `Stop`, `SubagentStop`: top-level `decision: block` with `reason` (required) prevents stopping; omit `decision` to allow. `hookSpecificOutput.additionalContext` is non-error feedback: the conversation continues so Claude can act on it, and the transcript labels it as hook feedback instead of a hook error. Both share the loop protections: `stop_hook_active`, and a cap of eight consecutive continuations after which Claude Code ends the turn.
- `PostToolBatch`, `PreCompact`: top-level `decision: block`.
- `TaskCompleted`, `TeammateIdle`: exit 2 with stderr as feedback, or `continue: false`.
- `SessionStart` also accepts `initialUserMessage`, `watchPaths`, `sessionTitle` and `reloadSkills`.

`decision` takes the single value `block`; to allow, leave it out. `additionalContext` is added as a system reminder: write factual statements ("This repo uses `uv run pytest`") rather than imperatives phrased as system commands, because text framed as an out-of-band command can trigger Claude's prompt-injection defenses and get surfaced to the user instead of used. Injected context is saved in the transcript and replayed on resume, so a value such as a commit hash goes stale; `SessionStart` runs again on resume.

Under `claude -p` a `PreToolUse` `ask` cannot be answered. Claude Code denies the call, and Claude reads the `permissionDecisionReason` in the tool result, so automated policy should land on `allow` or `deny`.

## Environment variables

- `CLAUDE_PROJECT_DIR` and `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` are exported to hook commands as well as substituted in `command` and `args`.
- `CLAUDE_ENV_FILE` exists only for `SessionStart`, `Setup`, `CwdChanged` and `FileChanged` hooks: `export` lines appended to it persist into later Bash commands. Other hook types do not have it.
- `CLAUDE_CODE_REMOTE` is `"true"` in remote web environments and unset in the local CLI. `CLAUDE_EFFORT` holds the effort level.
- `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises the eight-continuation cap on stop hooks.

## Gotchas

- An event name outside the list silently never fires; the validator flags camelCase spellings.
- A `Stop` or `SubagentStop` block with no `stop_hook_active` check loops until the cap ends the turn. Block once, then allow.
- `updatedToolOutput` changes what Claude sees, not the file or the command that already ran. A formatter hook edits the file itself and reports through `additionalContext`.
- Deny reasons, block reasons and `additionalContext` are read by Claude: write guidance, not error codes.
- Hooks are a supply-chain surface: a project's hooks run for everyone who works in it, and in `-p` runs without a trust dialog. Review them like CI config.
- Hooks run in their own session without a controlling terminal, so a script cannot open `/dev/tty`; use `systemMessage` or `terminalSequence`.
- Debug: `claude --debug-file PATH` writes hook execution details to a known file; `claude --debug` writes to `~/.claude/debug/SESSION_ID.txt` and prints nothing to the terminal.
