# Hook config, by example

Every shape this skill writes, with the matcher patterns that come up in practice. Facts are from the Claude Code hooks reference (snapshot 2026-10-03); check any file with `vibe-code hook validate FILE`. `assets/hooks.example.json` is a copyable `hooks` object for `.claude/settings.json` with the common entries.

## Contents

- The smallest complete file
- Matchers
- The `if` filter
- One script, several events
- Several handlers on one event
- The gate on Stop
- Background handlers
- HTTP handlers
- Personal and plugin files
- Where it loads from, and what to check

## The smallest complete file

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
            "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/guard.py"],
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

`hooks` maps an event name to a list of matcher groups; each group holds a `hooks` array of handlers. The event names are in `hook-facts.md`, and anything else silently never fires. With `args` set the command runs in exec form: no shell, `python3` is the executable, and the path placeholder is substituted as one argument with no quoting. Put the same hook in shell form only when it needs a pipe or `&&`, and then wrap the placeholder in double quotes:

```json
{"type": "command", "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/guard.py\"", "timeout": 5}
```

Set `timeout` on every handler. The default is 600 seconds, and a timed-out `PreToolUse` command hook does not block the call, so a slow check is a hole, not a gate. `shell` can be set to `bash` or `powershell` for shell-form commands; a Python script needs neither.

## Matchers

A matcher is read as an exact name or a `|` list when it has only letters, digits, `_`, `-` and spaces, and as an unanchored JavaScript regular expression otherwise. Only some events have one (the table is in `hook-facts.md`); a matcher on any other event is silently ignored.

Patterns worth copying:

```json
"matcher": "Bash"                         one tool, exact
"matcher": "Edit|Write"                   every tool that writes files, exact list
"matcher": "^(?!Bash$).*"                 everything except the shell
"matcher": "mcp__github__.*"              every tool of the github MCP server (the .* is required)
"matcher": "^(tf-reviewer|api-reviewer)$" two custom agents on SubagentStart
"matcher": "auto"                         PreCompact only when Claude Code compacts on its own
"matcher": ".envrc|.env"                  FileChanged: the literal file names to watch
```

A group without a matcher runs on every occurrence of its event. On `PreToolUse` that means a process launch per tool call, `Read` and `Glob` included, with the timeout risk on each; put a matcher on it unless the hook really is about every tool.

## The `if` filter

`if` holds exactly one permission rule and starts the process only on a match, which cuts launches further than a matcher can:

```json
{"type": "command", "if": "Bash(git *)", "command": "python3", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/git-guard.py"], "timeout": 5}
```

`Bash(git *)` matches when any subcommand of the input matches, leading `VAR=value` assignments are stripped, and a command Claude Code cannot analyze runs the hook anyway. There is no `&&` or list syntax: for two conditions write two handlers. `if` is evaluated on tool events only; on `SessionStart`, `Stop` and the rest a handler with `if` never runs. Because the filter is best-effort, a hard allow or deny belongs in `permissions` in settings, not in a hook.

## One script, several events

The payload names its event, so one script can back several entries and dispatch on `hook_event_name`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "python3", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/runner.py"], "timeout": 5}]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "python3", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/runner.py"], "timeout": 5}]
      }
    ]
  }
}
```

The template's `HANDLERS` table lists both events; an event the table lacks logs "no handler" and produces nothing.

## Several handlers on one event

All matching handlers run in parallel, and for `PreToolUse` the strictest decision wins (`deny`, then `defer`, `ask`, `allow`). Keep one concern per handler so a reviewer can read each alone. A handler that appears identically in two settings files runs once.

## The gate on Stop

```json
"Stop": [
  {"hooks": [{"type": "command", "command": "python3", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/gate.py"], "timeout": 180}]}
]
```

`Stop` has no matcher. The timeout has to cover the test run, and the script has to allow when `stop_hook_active` is true or the turn keeps continuing until Claude Code's eight-continuation cap ends it. The template's `block_once` does that. `PostToolBatch` is the cheaper moment for a formatter: one run after a parallel batch of edits, not one per edit.

## Background handlers

```json
{"type": "command", "command": "python3", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/track.py"], "async": true}
```

`async: true` runs the handler without blocking Claude, and its results arrive on a later turn. It cannot block or decide: `decision`, `permissionDecision` and `continue` have no effect, and Claude Code does not enforce `timeout` on it. `asyncRewake: true` runs in the background and wakes Claude on exit 2, with the stderr shown as a system reminder, for a long check that should interrupt only when it fails; `timeout` is still enforced there. Under `-p`, Claude Code kills async hooks still running at teardown.

## HTTP handlers

```json
{"type": "http", "url": "https://hooks.example.internal/claude", "headers": {"Authorization": "Bearer $HOOK_TOKEN"}, "allowedEnvVars": ["HOOK_TOKEN"], "timeout": 3}
```

The event JSON is the POST body, and the response body uses the output format of command hooks. Only a 2xx response with a JSON body can carry a decision; a non-2xx status, a connection failure or a plain-text body is a non-blocking error, so an HTTP handler is for telemetry, not enforcement. An `allowedHttpHookUrls` list in settings can restrict which URLs run.

## Personal and plugin files

Personal: the `hooks` key of `~/.claude/settings.json`, or of `.claude/settings.local.json` for one project, gitignored. There is no repository root to be relative to in the user file, so keep the script in `~/.claude/hooks/` and give its path in `args` with the home directory written out.

Plugin: `hooks/hooks.json` at the plugin root, with an optional `description`, scripts under `hooks/scripts/`, and the plugin-root placeholder:

```json
{
  "description": "Format files after edits",
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {"type": "command", "command": "python3", "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/scripts/format.py"], "timeout": 15}
        ]
      }
    ]
  }
}
```

`${CLAUDE_PLUGIN_ROOT}` is the plugin's install directory, which changes across updates; state that must survive one goes under `${CLAUDE_PLUGIN_DATA}`. The `hooks` key of `plugin.json` also loads. In `vibe-code hook validate`, a file named `hooks.json` is read as the plugin shape and any other name as a settings file; the project placeholder resolves only for a file directly under `.claude/`, and the plugin placeholder only under `hooks/`.

## Where it loads from, and what to check

Hooks merge from the user, project, local, managed and plugin levels; an identical handler in several settings files runs once. Edits to a settings file are normally picked up by a file watcher; `/hooks` lists active hooks with their source; `"disableAllHooks": true` turns off everything the user controls. `vibe-code hook validate FILE` runs `claude plugin validate` on the hooks first and then checks event spelling, handler fields, timeouts, matcher grammar and script paths.
