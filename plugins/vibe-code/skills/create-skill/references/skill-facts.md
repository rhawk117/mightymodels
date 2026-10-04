# Claude Code skill facts this skill depends on

Snapshot of the Claude Code documentation for skills, plugins and plugin evals taken 2026-10-03. A field or behavior outside this file is unverified: say so to the user instead of asserting it. Lines marked "unverified" have no supporting sentence in that snapshot.

## Contents

- Where skills live and how they are found
- How a skill gets loaded and what it costs
- Frontmatter fields
- Invocation flags
- allowed-tools
- String substitutions and the skill's own directory
- Dynamic context injection
- Skill content lifecycle
- Subagents and tool names
- Host and surface facts
- Skill or something else
- Body conventions

## Where skills live and how they are found

| Scope      | Path                                          | Loads in                                                                                |
| ---------- | --------------------------------------------- | --------------------------------------------------------------------------------------- |
| Enterprise | `.claude/skills/<name>/SKILL.md` in managed settings | all users on machines where the organization deploys it                          |
| Personal   | `~/.claude/skills/<name>/SKILL.md`            | all your projects on this machine, but not cloud or Cowork sessions                     |
| Project    | `.claude/skills/<name>/SKILL.md`              | sessions in this repository; commit it so the team gets it                              |
| Nested     | `<subdir>/.claude/skills/<name>/SKILL.md`     | sessions started in or below `<subdir>`; loads once Claude reads a file there           |
| Added dir  | `.claude/skills/<name>/SKILL.md` in a `--add-dir` directory | that session                                                      |
| Plugin     | `<plugin>/skills/<name>/SKILL.md`             | wherever the plugin is enabled, as `/plugin-name:name`                                  |

- Project skills load from `.claude/skills/` in the directory where Claude Code starts and in every parent directory up to the repository root, so in a monorepo say which level a skill belongs at.
- Same name in two of enterprise, personal and project: enterprise beats personal, personal beats project. A skill beats a file of the same name in `.claude/commands/`. A plugin skill never collides because it is namespaced `/plugin-name:name`.
- Do not name a skill folder `synced` or `anthropic-skills`; both are reserved.
- Check that a skill is visible by asking Claude "What skills are available?". For a plugin, `claude plugin details <plugin>` (run in the shell, with `--plugin-dir ./DIR` in the same command when the plugin is not installed) lists the component inventory and the projected always-on token cost.
- Live change detection covers SKILL.md text under an existing skills directory. A skills directory created after the session started needs `/reload-skills`. For a plugin, edits to hooks, `.mcp.json` and agents need `/reload-plugins`; develop with `claude --plugin-dir ./DIR` and run `/reload-plugins` after adding a component.
- Cloud and browser sessions do not run bundled scripts (unverified: no sentence in the snapshot says it; claude.ai and Cowork are documented to reject a plugin with a top-level `bin/`). A skill that depends on a script should say so in `compatibility` and keep a prose fallback.

## How a skill gets loaded and what it costs

- Every session lists each enabled skill's name and description in context, whether or not the skill is ever used. The full body loads only when the skill is invoked, by a description match or by `/name`.
- The listing budget is 1% of the context window (`skillListingBudgetFraction`). When it overflows, descriptions are dropped starting with the least-invoked skills, which removes the keywords Claude matches on. `claude plugin details <plugin>` shows what a plugin adds.
- `description` and `when_to_use` are joined in the listing and truncated at 1,536 characters together, so put the key use case first. The validator in this plugin also caps `description` alone at 1024 characters and `name` at 64 characters, and `name` must equal the directory.
- The description is the entire trigger surface. Everything about when to use the skill goes there, because the body is read only after the decision to load it.

## Frontmatter fields

All fields are optional; only `description` is recommended. A field name must match exactly, hyphens included: Claude Code ignores an unknown field without an error, so the validator rejects unknown keys to catch typos. The 20 known keys are the rows below.

| Field                      | Meaning                                                                                                   |
| -------------------------- | --------------------------------------------------------------------------------------------------------- |
| `name`                     | command name; defaults to the directory name                                                              |
| `description`              | what it does and when to use it; the trigger text                                                         |
| `when_to_use`              | extra trigger phrases or example requests, appended to the description in the listing                     |
| `argument-hint`            | autocomplete hint such as `[issue-number]`; write it as a quoted string                                   |
| `arguments`                | named positional arguments for `$name` substitution; a space-separated string or a YAML list             |
| `disable-model-invocation` | `true` stops Claude loading the skill itself; human-only via `/name`                                      |
| `user-invocable`           | `false` hides it from the `/` menu; model-only                                                            |
| `allowed-tools`            | pre-approves tools during the turn that invokes the skill                                                 |
| `context`, `agent`         | `context: fork` runs the skill as the prompt of a new subagent of type `agent`                            |
| `hooks`                    | hooks registered when the skill is invoked, kept for the rest of the session                              |
| `paths`                    | glob patterns that limit automatic activation to matching files; comma-separated string or YAML list     |
| `metadata`                 | free-form map of strings for your own tooling                                                             |
| `license`, `compatibility` | spec fields Claude Code accepts and ignores; `compatibility` is at most 500 characters                    |

The table lists the fields this skill guides on. The docs define five more that it does not guide on; the validator accepts all 20 documented keys.

Fields from other hosts that do not belong to skills are errors under the validator: `target`, `mcp-servers`, `handoffs`, `tools`, `agents`. A skill cannot declare an MCP server.

Outside Claude Code the spec's fields are `name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools`. `argument-hint`, `disable-model-invocation` and `user-invocable` are native to Claude Code; packaging for claude.ai upload or the Skills API rejects them with "Unexpected key(s) in SKILL.md frontmatter". Mention this only when the user plans to upload.

Frontmatter is read only when the opening `---` is the first line of the file. If the YAML does not parse, the skill still loads with no fields set, so `/name` works but Claude cannot match the description.

## Invocation flags

Boolean fields accept `true`, `false`, `yes`, `no`, `on`, `off`, `1` and `0` in any letter case.

| `disable-model-invocation` | `user-invocable` | result                                                                                          |
| -------------------------- | ---------------- | ----------------------------------------------------------------------------------------------- |
| false                      | true (defaults)  | Claude loads it on a description match; a human can run `/name`                                 |
| true                       | true             | human-only; also blocks preloading into subagents and scheduled-task runs                       |
| false                      | false            | model-only; hidden from the `/` menu and not run when typed                                     |
| true                       | false            | dead: nobody can invoke it; the validator rejects the pair (the docs table has no row for this pair, so the rule is this plugin's own) |

## allowed-tools

- Accepts a space- or comma-separated string or a YAML list of permission rules: `Bash(git add *)`, `Bash(uv *)`, `Edit`, `Write`, `WebFetch(domain:docs.example.com)`, MCP tools as `mcp__<server>__<tool>`.
- It pre-approves tools for the turn that invokes the skill and clears at the next message. It does not restrict anything: every tool stays callable and permission settings still govern the rest.
- Workspace trust does not gate the field, and a skill can grant itself broad access, so keep the list to the narrowest rules the procedure needs.
- A skill that bundles a script needs the interpreter pre-approved too, for example `Bash(python3 *)`, or every run prompts for it.
- Write the rule with the same `${CLAUDE_SKILL_DIR}` path the body uses so a bundled script runs without a prompt.
- The plugin this skill ships in sets none; the user decides for their own skill.

## String substitutions and the skill's own directory

These are replaced in the rendered SKILL.md text (and in `allowed-tools` Bash rules for the two directory variables). They are not replaced in files SKILL.md points at, so a skill that needs to show one literally keeps it in a reference file.

| Placeholder                                   | Value                                                                                      |
| --------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `$ARGUMENTS`                                  | everything typed after the skill name; appended as `ARGUMENTS: <value>` when unused       |
| `$ARGUMENTS[N]`, `$N`                         | the argument at 0-based position N; shell-style quoting groups words                       |
| `$name`                                       | a named argument declared in `arguments`                                                   |
| `${CLAUDE_SESSION_ID}`                        | the session id                                                                             |
| `${CLAUDE_EFFORT}`                            | the active effort level                                                                    |
| `${CLAUDE_SKILL_DIR}`                         | the directory holding the skill's SKILL.md; for a plugin skill, the skill's own subdirectory |
| `${CLAUDE_PROJECT_DIR}`                       | the project root                                                                           |
| `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}` | the plugin's install directory and its persistent data directory (plugin skills only)  |

- Reach bundled files with `${CLAUDE_SKILL_DIR}/scripts/NAME` in the body, so the path resolves from any working directory. Use `${CLAUDE_PLUGIN_ROOT}` for plugin-wide files outside the skill.
- A subagent does not inherit the loaded skill, so pass it the resolved paths in the dispatch message.
- Write `\$1.00` to keep a literal dollar sign before a digit, `ARGUMENTS` or a declared name.

## Dynamic context injection

A bang followed by a backtick-quoted shell command, on its own line or after whitespace, runs before the skill is sent to Claude and is replaced by the command's output, so Claude receives data rather than the command. Use it for live state a skill always needs (a diff, a branch name, a file listing).

- It runs on every invocation, on the user's machine, with the working directory of the session shell, so give it paths through `${CLAUDE_SKILL_DIR}` or `${CLAUDE_PROJECT_DIR}`.
- Output is inserted as plain text and is not scanned again.
- Substitution runs over the whole SKILL.md, including examples, so a skill that documents the syntax keeps its examples in a file under `references/`.
- A failing command surfaces its error in the skill content; keep injected commands short and read-only.
- `assets/SKILL.template.md` carries one placeholder line of this form in its Context section; delete the section when the skill needs no live data.

## Skill content lifecycle

- A rendered SKILL.md enters the conversation as one message and stays for the rest of the session. Claude Code does not re-read the file on later turns, so write guidance that applies throughout a task as a standing instruction ("run the tests after every edit") rather than a one-time step ("run the tests").
- After auto-compaction only the first 5,000 tokens of each invoked skill are re-attached, within a 25,000-token combined budget filled from the most recent skill. Put the most important instructions near the top.
- A rule that must hold every time belongs in a hook, not in skill prose, because a hook runs whenever its event occurs. A hook scoped to the skill goes in the `hooks` frontmatter field and applies from invocation to the end of the session.

## Subagents and tool names

- Claude Code delegates through the `Agent` tool, renamed from `Task` in version 2.1.63; `Task(...)` in settings and agent definitions still works as an alias. Custom subagents live in `.claude/agents/` and `~/.claude/agents/`; a plugin ships them as `agents/<name>.md`, invoked as `plugin-name:name`.
- `context: fork` with `agent: <type>` runs the skill body as the prompt of a fresh subagent that does not see the conversation. It only suits a skill whose body is an explicit task; guidance without a task returns nothing useful.
- Tool names in matchers, graders and `allowed_tools`: `Bash`, `Read`, `Write`, `Edit`, `WebFetch`, `WebSearch`, `Skill`, `Agent`, `Grep`, `Glob`.

## Host and surface facts

| Concern                 | Claude Code                                                    |
| ----------------------- | -------------------------------------------------------------- |
| Headless run            | `claude -p "<prompt>"`; `/skill-name` in the prompt is expanded |
| Explicit invocation     | `/skill-name`, or `/plugin-name:skill-name` for a plugin skill |
| Subagents               | the `Agent` tool and `.claude/agents/`                         |
| Skill-scoped hooks      | `hooks` frontmatter                                            |
| Plugin launcher on PATH | files in the plugin's `bin/` are on the shell PATH while the plugin is enabled |

- While a plugin is enabled, its `bin/` folder is on the PATH of the shell Claude runs commands in, so a skill's instructions can run a launcher such as `vibe-code` by name with nothing installed by the user.

## Skill or something else

| Need                                                                                 | Mechanism                                              | Sibling skill       |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------ | ------------------- |
| a persona, delegation target, own tool set, own model or own MCP server              | subagent: `agents/<name>.md`                           | `create-subagent`   |
| something that must happen at a lifecycle point whether or not Claude follows a skill | hook: `hooks/hooks.json`, or `hooks` frontmatter       | `create-hooks`      |
| always-on steering for certain files, no procedure to run                            | `CLAUDE.md` or `.claude/rules/*.md` (a plugin cannot ship rules) | `create-instructions` |
| an MCP server the skill's tools come from                                            | `.mcp.json` at the plugin root                         | `create-mcp`        |
| a task that needs its own context window                                             | the skill itself, with `context: fork` and `agent`     | this skill          |

## Body conventions

- Frontmatter first, then Markdown. Keep SKILL.md under 500 lines and move detail into files the body points at, with a sentence saying when to read each.
- Layout: `references/` for material loaded on demand, `scripts/` for deterministic code Claude runs instead of re-deriving, `assets/` for templates and files that end up in outputs. Empty directories are not created. Eval cases do not live in the skill: they live in `evals/` at the plugin root.
- Three loading levels: name and description always; the body when the skill fires; bundled files when the body points at them. Keep references one level deep: a reference that points at another reference loses the thread.
- Explain why next to an instruction rather than shouting. Capitals are a smell: when a behavior keeps failing, prefer a gate, a script that refuses to proceed or a check the agent must run.
- Skip what Claude already knows; spend context on conventions, formats and edge cases it could not have known. Name one default and mention the alternative in a clause.
