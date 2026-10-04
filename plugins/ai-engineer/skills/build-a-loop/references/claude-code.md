# Claude Code wiring

How to enforce a loop contract in Claude Code. The facts below come from the Claude Code docs as snapshotted on 2026-10-03. A line marked unverified has no supporting docs sentence: say so to the user instead of asserting it. Confirm event names and flags against the current docs before shipping.

## Contents

- Choosing what starts the next turn
- Goal-based loops
- Running it unattended
- Budgets and caps
- The stop gate
- Keeping the contract alive through compaction
- The verifier subagent
- Parallel workers

## Choosing what starts the next turn

| Approach | Next turn starts when | Stops when |
| --- | --- | --- |
| `/goal` | the previous turn finishes | a model judges the condition met or impossible, an error you must fix clears it, or you run `/goal clear` |
| `/loop` | a time interval elapses | you stop it, or Claude decides the work is done |
| Stop hook | the previous turn finishes | your own script or prompt decides |

`/goal` and a Stop hook both fire after every turn. `/goal` is built on a session-scoped prompt-based Stop hook.

`/loop [interval] [prompt]` re-runs a prompt on a timer while the session stays open. Leave the interval out and Claude picks one. Leave the prompt out and Claude runs `loop.md` (`.claude/loop.md` in the project wins over `~/.claude/loop.md`), or a built-in maintenance prompt when neither exists. A prompt given on the command line replaces `loop.md`. Edits to `loop.md` apply on the next iteration.

For work that must run with no session open, schedule it:

| | Cloud routine | Desktop scheduled task | `/loop` |
| --- | --- | --- | --- |
| Needs your machine on | no | yes | yes |
| Needs an open session | no | no | yes |
| Local files | no, a fresh clone | yes | yes |
| Minimum interval | 1 hour | 1 minute | 1 minute |

Use a routine or a scheduled task for the event-driven and overnight shapes in step 2 of the skill.

## Goal-based loops

`/goal <condition>` runs the loop until an evaluator judges the condition met. The evaluator is a separate small fast model that **does not call tools**, so it can only judge what the main agent has already said out loud in the conversation.

That single fact decides how to write the condition. It must be demonstrable from the agent's own output:

- Good: `all tests in tests/api pass, with the pytest summary line shown, and ruff reports no errors`
- Bad: `the API is production ready`
- Bad: `the code is clean` (nothing the evaluator can see)

The condition can be up to 4,000 characters. State one measurable end state, the check that proves it, and anything that must not change on the way.

Three verdicts: met, not yet, and **impossible**, where the evaluator judges the condition can never be satisfied. The impossible verdict clears the goal and records the reason, which is the give-up path every loop needs.

Bound the run inside the condition itself: append `or stop after 20 turns`.

Stall detection is built in. Several turns with no tool use stops the loop, warns, and hands back control with the goal still set.

Escalation is mostly sorted for you. Auth failure, exhausted credit balance, a context overflow auto-compaction could not clear, and an unavailable model all clear the goal and return to the human. After any other failure the goal stays set. In an interactive session an overloaded server or a dropped connection is retried, and the goal pauses after three failed retries. A rate limit pauses it at once.

Three behaviors that surprise people:

- While a subagent or a background command is still running at the end of a turn, Claude Code skips the evaluation for that turn.
- After 30 minutes of such waiting a check-in is due. `CLAUDE_CODE_GOAL_CHECKIN_MINUTES` changes the interval, and `0` turns check-ins and automatic retries off.
- A goal still active when a session ends is restored on `--resume` and `--continue`. The turn count and timer reset.

Run a goal without a session open with `claude -p "/goal <condition>"`. It runs to completion in one call.

## Running it unattended

`claude -p "<prompt>"` (long form `--print`) runs one non-interactive session. These flags work in print mode only:

| Need | Flag |
| --- | --- |
| Cap the agentic turns, exits with an error at the limit | `--max-turns N` |
| Cap the spend, subagent spend included | `--max-budget-usd N` |
| Plan without editing | `--permission-mode plan` |
| Nobody to answer permission prompts | `--permission-prompts none` |
| Validated verdict object | `--json-schema '<schema>'` |

Permissions need a decision before nobody is watching. Allow the narrow set the loop needs, for example `--allowedTools "Bash(git *)"`, and deny the dangerous one, for example `--disallowedTools "Bash(git push *)"`. Deny is checked before ask and allow. `--permission-mode dontAsk` or `auto` removes per-tool prompts. `--permission-prompts none` denies the prompts nobody can answer and removes `AskUserQuestion`, so the loop cannot stall waiting for a person. `--dangerously-skip-permissions` skips every prompt: avoid it unless the run is sandboxed.

`--bare` skips hooks, skills, subagents, plugins, MCP servers, auto memory and `CLAUDE.md`. It gives the same result on every machine, and it also skips your stop gate and any hook-based safeguard, so a bare run needs its check inside the prompt or the calling script. A bare run does not use your subscription login: set `ANTHROPIC_API_KEY`.

To watch a long run, add `--output-format stream-json --verbose`. The first event, `system/init`, reports the model, tools, MCP servers and loaded plugins, so a plugin that did not load shows up there. Add `--include-hook-events` to see hook lifecycle events. The final result carries a `subtype` to branch on.

`--worktree <name>` starts the run in an isolated git worktree at `<repo>/.claude/worktrees/<name>`. Give each parallel worker its own.

`claude --cloud "<task>"` starts a cloud session. Whether it opens a branch or a draft pull request was not checked.

## Budgets and caps

Both SDK budgets default to **no limit**, and `--max-turns` also defaults to none. Set them for anything unattended:

- `max_turns` counts tool-use turns only
- `max_budget_usd` caps spend

Termination is an enum, not a boolean. Handle `success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries`. The `result` field is present only on `success`, so code that reads it unconditionally will break exactly when the loop failed.

Subagent trees have separate caps, and prompting is not a substitute for setting them:

- `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3
- `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, default 20. At the limit the spawn fails with `Concurrent subagent limit reached`.
- `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` for workflow scripts
- a spend cap, which refuses further spawns once reached

A subagent that hits its own `maxTurns` returns partial output and can be resumed rather than failing outright.

## The stop gate

A `Stop` hook runs when Claude finishes responding and can block it, forcing another turn. This is where a test suite belongs when "done" must mean "the tests pass". `SubagentStop` does the same for a subagent.

Choose the handler by how the check is made:

| Handler | Use when |
| --- | --- |
| `command` | the check is deterministic: a test run, a linter, a script that prints a number |
| `prompt` | the payload alone is enough for a model to judge; `/goal` is one of these |
| `agent` | the check needs to read files or run commands; experimental, so prefer `command` in production |

How a stop hook blocks:

- Print `{"decision":"block","reason":"..."}` on stdout and exit 0. `reason` is required.
- Or exit 2 with the message on stderr. Claude receives it as the reason to continue.
- Any other exit code does not block.

Claude Code overrides the hook after **8 consecutive continuations**, so the loop cannot be trapped. `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises that cap. You still want your own escape: the payload field `stop_hook_active` is `true` while Claude continues because of a stop hook. Read it and downgrade from blocking to advisory once it is set, so a check that can never pass degrades into a warning instead of eight wasted turns.

`assets/verify_gate.py` does this for a command hook. It reads `.loop-gate.json` and runs the check without a shell. On failure it blocks, counting `stop_hook_active` as one earlier block, and once `max_blocks` is reached it releases the turn with `{"systemMessage":...}`. That release message goes to the user, not to Claude.

| Key or variable | Meaning |
| --- | --- |
| `check` | the check as an argument list, for example `["uv", "run", "pytest", "-q"]` |
| `cwd` | where to run it, default `.` |
| `state_path` | the block counter, default `.loop-gate.state` |
| `max_blocks` | blocks before it releases, default 1 |
| `LOOP_GATE_CONFIG` | config path, default `.loop-gate.json` |
| `LOOP_GATE_TIMEOUT` | seconds the check may run, default 300 |

Command hooks default to a 600-second timeout, so a gate that runs a test suite fits. If you set `timeout` on the hook, keep it above `LOOP_GATE_TIMEOUT`. Copy the script to `.claude/hooks/verify_gate.py` and wire it in `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/verify_gate.py"],
            "timeout": 330
          }
        ]
      }
    ]
  }
}
```

A plugin ships the same `hooks` object in `hooks/hooks.json`, with `${CLAUDE_PLUGIN_ROOT}` in the script path. Hooks also live in `~/.claude/settings.json`, `.claude/settings.local.json`, managed policy settings, and skill or subagent frontmatter. The setting `disableAllHooks` turns them off, except managed ones. To author or test a hook, use the `create-hooks` skill: it holds the checked event, payload and output facts, so this page does not repeat them.

Event names are PascalCase: `Stop`, `SubagentStop`, `PreToolUse`, `PostToolUse`, `PreCompact`, `PostCompact`, `SessionStart`. A matcher string names tools joined with a vertical bar.

A prompt-based stop gate needs no script:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Check if all tasks are complete. If not, respond with {\"ok\": false, \"reason\": \"what remains to be done\"}."
          }
        ]
      }
    ]
  }
}
```

Hooks run in the application process, not in the context window. Only what a hook returns to Claude enters the conversation, and a hook that fires again after compaction does so independently of the summary. Context a hook added earlier is summarized with the rest of the conversation, so a hook is not a place to park rules the agent must keep seeing.

`PreToolUse` hooks block a tool call before it runs. Use `hookSpecificOutput.permissionDecision` to deny, or `hookSpecificOutput.updatedInput` to rewrite the arguments. That the agent receives the rejection as the tool result is unverified. Use this to enforce read-before-write on the contract file: no criterion flips to true unless the evidence artifact was read first.

`PostToolUse` can replace a tool's output with `updatedToolOutput` before Claude sees it. Its `additionalContext` appends instead, up to 10,000 characters. A `PostToolUseFailure` hook that exits 2 shows its stderr to Claude.

## Keeping the contract alive through compaction

Compaction clears older tool outputs first, then summarizes. Requests and key snippets survive; detailed instructions from early in the conversation may not. `/context` shows what fills the window, and `/compact [instructions]` compacts by hand with a focus. No documented Claude Code setting matches a fixed percentage threshold for compaction.

Claude Code has no list of past compactions. A `PostCompact` hook receives the compacted state, so log the generated summary there when you need to see what was lost. `/rewind` undoes file edits and does not list compactions.

Defenses, in order of strength:

1. Put standing rules in `CLAUDE.md`. The project-root file and auto memory survive compaction and reload from disk; instructions given only in conversation may be lost.
2. Add a section titled `Compact Instructions` to `CLAUDE.md` naming the contract and the criteria as must-keep. The header text is the documented name. Whether the compactor matches other wording is unverified.
3. Snapshot the contract with a `PreCompact` hook and re-inject it with a `SessionStart` hook whose matcher is `compact`. Claude Code runs it after compaction and adds its output to the compacted context.

```json
{
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cp",
            "args": ["${CLAUDE_PROJECT_DIR}/LOOP.md", "${CLAUDE_PROJECT_DIR}/.loop-snapshot.md"],
            "timeout": 10
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "cat",
            "args": ["${CLAUDE_PROJECT_DIR}/.loop-snapshot.md"],
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Keep noisy output out of the window in the first place: quiet flags on chatty commands, or run them inside a subagent. Running tests, fetching documentation and processing logs can consume a lot of context.

## The verifier subagent

Write the grader as a subagent file: `.claude/agents/<name>.md` for a project, `~/.claude/agents/<name>.md` for every project on the machine, or `agents/` in a plugin. The frontmatter `description` is what Claude uses to decide when to delegate, so say what it grades. The fields that matter here are `name`, `description`, `tools`, `disallowedTools`, `model`, `skills` and `maxTurns`. The `create-subagent` skill covers the file in full.

```markdown
---
name: loop-verifier
description: Grades a finished iteration against the criteria in LOOP.md and reports which are met. Use after the loop claims success.
tools: Read, Grep, Glob
---
```

Give it no `Write` or `Edit`: list only the tools it needs in `tools`, or name those two in `disallowedTools`. A withheld tool is absent from its session, with no prompt or error, so this is a hard guarantee rather than an instruction. Omit `tools` and it inherits every tool.

Subagents do not inherit your skills' content. Frontmatter `skills` preloads full skill content, and a subagent can still invoke unlisted project, user and plugin skills through the Skill tool.

Give it the diff and the criteria and nothing else. The value comes from what it cannot see: it never saw the reasoning that produced the change, so it judges the result on its own terms. The only channel from parent to subagent is the Agent tool's prompt string. File paths, error messages, and decisions the verifier needs must be in that string. A forked subagent is the exception: it copies the conversation, which defeats the isolation you want here.

To get a verdict a script can read, run the verifier as its own print-mode call with `--json-schema`: it returns JSON that matches the schema after the run completes, for example `{"criterion": "...", "met": true, "evidence": "..."}`.

Guard against the reviewer that finds problems because it was asked to. Have it grade against the named criteria and report "criterion met" as readily as it reports gaps, and distinguish a refuted claim from one it could not check.

## Parallel workers

Subagents run through the Agent tool, one per unit. `/batch <instruction>` researches the codebase, splits the work into 5 to 30 independent units, and after you approve the plan spawns one background subagent per unit, each in an isolated worktree. A subagent starts in the main working directory unless its frontmatter sets `isolation: worktree`.

Workflow scripts hold the loop outside the conversation, so intermediate results stay in script variables instead of filling the context window. Reach for them when the number of iterations is large or the branching is mechanical.

Runtime caps: 16 concurrent agents by default (fewer on a machine with fewer CPUs, and up to 256 with `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`), 4,096 items per parallel call, 1,000 agents per run. A run of more than 25 agents shows a size warning, which is advisory and does not pause anything.

Prefer progress-phrased stop conditions in fan-out loops: "keep fixing reported errors until the type check passes or two rounds in a row make no progress". This is design advice from the skill author, not a docs claim.

## Checking this page

Check event names against the hooks reference in the Claude Code docs. `claude --help` is a second source for flags; that it lists current hook events is unverified.
