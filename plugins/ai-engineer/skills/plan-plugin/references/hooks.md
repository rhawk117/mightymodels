# Hooks (`hooks/hooks.json`)

Sources: Claude Code docs, plugins/components (Hooks), plugins/manifest-reference (hooks), hooks (events table, exit codes, Stop, `disableAllHooks`). Builder: `create-hooks`, whose reference lists every event and payload.

## What it is

A JSON file mapping lifecycle events to handlers. Handler types are `command`, `http`, `mcp_tool`, `prompt` and `agent`. Save it at `hooks/hooks.json` under a top-level `"hooks"` key, the same shape as the `hooks` object in `settings.json`; a file holding only the event map without that wrapper fails to load. Hooks in `hooks/hooks.json` and in the `hooks` manifest key both load. Claude Code registers a plugin's hooks when a session loads the plugin and they fire on their events from then on, so plugin hooks run for every user of the plugin in every repository; narrow the `matcher` to limit when.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/uv-runner.py"],
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{ "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/scripts/format.sh\"" }]
      }
    ]
  }
}
```

With `args`, the handler is exec form: `command` is spawned directly with each `args` element as one argument and no shell, so path variables need no quoting. Without `args` it is shell form and the `${CLAUDE_PLUGIN_ROOT}` path needs double quotes. `timeout` is in seconds. `scripts/` is a convention, not a directory Claude Code looks for; the hook points at the file by path.

## Events

The events a plan most often uses are PascalCase: `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `UserPromptExpansion`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PostToolUseFailure`, `SubagentStart`, `SubagentStop`, `Stop`, `StopFailure`, `PreCompact` and `Notification`. The hooks page lists more (for example `Setup`, `PostToolBatch`, `TaskCreated`, `InstructionsLoaded`, `PostCompact`); read it, or the create-hooks reference, before naming one that is not here.

Two names are matches by name only: `UserPromptExpansion` fires when a typed command expands into a prompt and can block the expansion, and `StopFailure` fires when a turn ends on an API error and ignores output and exit code except `terminalSequence`. An earlier toolkit carried event names with no payload documented for them, so confirm the match against the hooks page before relying on either.

| event | when it fires | can block |
| --- | --- | --- |
| `PreToolUse` | before a tool call executes | yes, exit code 2 blocks the call |
| `PostToolUse` | after a tool call succeeds | no; stderr is shown to Claude |
| `Stop` | when Claude finishes responding | yes, exit code 2 or `decision: "block"` keeps the conversation going |
| `SessionStart` | when a session begins or resumes | no; stderr to the user only |

## Matchers

A matcher on a tool event is the tool name: `Bash`, `Edit|Write`, `mcp__.*`. A tool from an MCP server the plugin declares is `mcp__plugin_<plugin>_<server>__<tool>`, and a matcher on the server name alone never fires. `UserPromptSubmit`, `Stop` and some other events take no matcher and always fire.

## Runtime facts

- Exit code 2 is the signal that blocks. Without valid JSON on stdout, any other non-zero code (1 included) is a non-blocking error and the action proceeds, so a hook that enforces a policy must `exit 2`.
- A hook that reaches its `timeout` is cancelled and on most events renders no decision.
- Every hook process receives `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA`, plus `CLAUDE_PLUGIN_OPTION_<KEY>` for each `userConfig` value.
- Run `/reload-plugins` after changes. `"disableAllHooks": true` in a settings file turns every hook off for testing; it cannot disable managed hooks.
- Whether `prompt` handlers run in a `-p` session is not documented in the pages read for this plan; check before relying on one.
- Hook entries merge across levels, so the same hook at two levels runs twice.

## Gate "done" with `Stop`

The input to a `Stop` hook carries `stop_hook_active`, which is `true` when Claude Code is already continuing because of a stop hook. A hook that returns `{"decision": "block", "reason": "..."}` without checking it can block on a condition that never resolves; check the field (or the transcript) and let the turn end the second time. Claude Code caps consecutive stop-hook continuations at eight and then ends the turn (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises the cap).

## When a hook is the right mechanism

A fixed, repeatable action at a known moment: rewrite a command, format after an edit, inject repository state at session start, gate Claude's "done" on a check, record events. Not: a static blocklist, which is a `permissions.deny` rule in the project `.claude/settings.json` such as `Bash(terraform apply *)` (record it in `outside_plugin`; a plugin cannot ship permissions); a procedure with judgement (skill or agent); steering that must always be present (project rule file, outside the plugin). Ask whether every user in every repository should get the hook.

## Plan snippet

- ships in `hooks/hooks.json` under the event, with the script in `scripts/<name>.py` called through `${CLAUDE_PLUGIN_ROOT}`; runs for every user of the plugin
- exit code 2 blocks; any other failure does not; run `/reload-plugins` after changes
- a `Stop` gate checks `stop_hook_active`
- a static blocklist belongs in `permissions.deny`, not a hook
