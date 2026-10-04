---
name: plan-plugin
description: Planning interview for a Claude Code plugin; ends in a phased plan and an empty plugin shell, never a build. Use whenever the user wants to create, design, plan, scope or extend a Claude Code plugin, says "I want a plugin that...", "bundle our X conventions", "package this for the team", "what should go in the plugin", or describes several customisations at once for one purpose, even without the word "plugin". Asks what problem the plugin solves and for whom, classifies it, settles name, keywords, identity and distribution, interviews one kind at a time across what a plugin can ship (skills, commands, agents, hooks, MCP servers, LSP servers, executables, output styles), discourages wrong mechanisms while recording the user's decision, shows the layout tree for confirmation, and writes PLAN.md (Human section with build phases and one fenced prompt per session; Agent section of greppable facts), plugin-plan.json and the shell for the create-* builder skills to fill later.
license: MIT
argument-hint: "[what the plugin is for]"
---

# Plan a Claude Code plugin

A plugin is a bundle: skills, single-purpose agents, hooks, MCP servers, language servers, executables, output styles, shipped under one name so a team installs one thing. The decomposition is the work. Decide it in one sitting with the person who knows the problem, and each piece becomes a short, well-specified session for the builder skill that owns it. Decide it piece by piece across sessions and the plugin drifts: a hook that duplicates a skill, an agent with no distinct job, an MCP server that wraps commands Claude already runs. So this skill is an interview that produces a record, a phased plan and an empty shell, and deliberately builds nothing else.

Ask every question with the `AskUserQuestion` tool: single select, multi select, or free text through its other option. In a `-p` run the tool is offered only when the run has a permission host, so the interview cannot run unattended.

| phase                   | what happens                                                                         | user involvement                   |
| ----------------------- | ------------------------------------------------------------------------------------ | ---------------------------------- |
| A. Start                | new plugin or extension of one; inventory when it exists                             | one question                       |
| B. Problem and audience | what goes wrong today; who uses the plugin and how                                   | free text, one confirmation        |
| C. Kind                 | ecosystem harness, domain knowledge, workflow, integration; one or two               | one question                       |
| D. Identity             | name, keywords, description, license, author, homepage, repository, config values    | one question                       |
| E. Components           | one round per kind a plugin can ship, one round per instance                         | several questions                  |
| F. Challenge            | per component: is this the right mechanism; advice and the user's decision recorded  | one decision per flagged component |
| G. Layout               | the tree the record implies, shown for confirmation                                  | one confirmation                   |
| H. Distribution         | marketplace or local; install command                                                | one question                       |
| I. Record and shell     | plan JSON validated; PLAN.md, manifest, README, directories                          | one confirmation to write          |
| J. Hand off             | the phases, what to run first, what is unverified                                    | summary                            |

## The kinds

Each kind a plan can carry, the builder skill that owns it, and the file the component writes. A kind with `manual` has no builder: the plan records the entry and its session is a short hand-written one. `ai-engineer plugin validate` accepts exactly these eight kinds.

| kind         | builder           | files                                                  | reference                      |
| ------------ | ----------------- | ------------------------------------------------------ | ------------------------------ |
| skill        | `create-skill`    | `skills/<name>/SKILL.md`                               | `references/skills.md`         |
| command      | `create-skill`    | `skills/<name>/SKILL.md` with `argument-hint`          | `references/commands.md`       |
| agent        | `create-subagent` | `agents/<name>.md`                                     | `references/agents.md`         |
| hook         | `create-hooks`    | `hooks/hooks.json`, `scripts/<name>.py`                | `references/hooks.md`          |
| mcp          | `create-mcp`      | `.mcp.json`, `mcp/<name>/`                             | `references/mcp.md`            |
| lsp          | manual            | `.lsp.json`                                            | `references/lsp.md`            |
| executable   | manual            | `bin/<name>`                                           | `references/executables.md`    |
| output-style | manual            | `output-styles/<name>.md`                              | `references/output-styles.md`  |

Two things people ask for are not plugin components, and `plugin validate` rejects the kinds `rule` and `extension` with a message naming `outside_plugin`:

- Always-on guidance. Claude Code does not load a `CLAUDE.md` at the plugin root, and a plugin cannot ship project rules. Record an `outside_plugin` entry whose mechanism is a project rule file `.claude/rules/<name>.md` (a `paths` list in its YAML frontmatter scopes it to matching files) or the project `CLAUDE.md`. Guidance that Claude should load when it applies can instead be a skill.
- An extension. A plugin has no extensions directory and the manifest has no key for one. Ask what the extension was meant to do and plan the need as a hook, an MCP server or an executable, or record it under `outside_plugin`.

The old kind name `worker` is called `agent`; `plugin validate` says so.

## References

One file per thing a plugin can ship, each with what it is, where it lives, its frontmatter or schema, the runtime facts that constrain it, when it is the right mechanism, and the plan snippet the record carries. Read `references/layout.md` at the start and read a kind's file when its round in phase E begins and again when phase F challenges a component of that kind. Advice in the interview comes from these files, not from memory.

| file                            | covers                                                                                          |
| ------------------------------- | ----------------------------------------------------------------------------------------------- |
| `references/layout.md`          | the tree, namespacing, precedence per kind, load and reload, cache, checking a plugin           |
| `references/manifest.md`        | `.claude-plugin/plugin.json` keys, reserved names, `userConfig`, `dependencies`, README, LICENSE |
| `references/skills.md`          | `skills/<name>/SKILL.md` frontmatter and when a skill is the right mechanism                    |
| `references/commands.md`        | the command kind: a skill with `argument-hint`, and what `commands/` still is                   |
| `references/agents.md`          | `agents/<name>.md`, fields a plugin agent supports and ignores, names                           |
| `references/hooks.md`           | `hooks/hooks.json`, events, matchers, exit codes, the `Stop` gate                               |
| `references/mcp.md`             | `.mcp.json`, names, variables, what `plugin validate` checks                                    |
| `references/lsp.md`             | `.lsp.json`, `extensionToLanguage`, what validate does not read                                 |
| `references/executables.md`     | `bin/`, the Bash tool's `PATH`, the claude.ai and Cowork limit                                  |
| `references/output-styles.md`   | `output-styles/<name>.md`, `keep-coding-instructions`, `force-for-plugin`                       |
| `references/marketplace.md`     | channels, `marketplace.json`, `sha` pinning, settings that live beside a plugin                 |

`assets/plan.example.json` is a record that passes `plugin validate --strict`; copy its shape.

The rule for the whole workflow: anything the user has not said is a question, not an assumption. When the user answers everything upfront ("everything you'd otherwise ask me: ..."), use those answers, skip the questions, and say which default you took for anything not covered.

## Phase A: start

Ask whether this is a new plugin or an addition to one that exists, and where it lives. For an existing plugin run `ai-engineer plugin inventory PLUGIN_DIR --out plugin-plan.json`. It reads `.claude-plugin/plugin.json` and every component location in the layout (skills, agents including subfolders, `commands/`, `hooks/hooks.json`, `.mcp.json`, `.lsp.json`, `bin/`, `output-styles/`, and the manifest's path overrides) and records what is there as `built`, with the files each one owns. Fields the manifest lacks are filled with placeholder text so the record validates; say so when showing it. Show the inventory as a table and say that the interview covers only additions and changes. If a `plugin-plan.json` already exists, read it first: earlier decisions and open questions are the starting point, not something to re-ask.

## Phase B: problem and audience

Two things in the user's words, restated and confirmed:

- What goes wrong today without the plugin. Push past "help with Python": the record needs a failure someone recognises ("Claude runs bare pytest and skips ruff; reviewers catch it late"). Every component later has to trace back to this sentence, and a component that does not is the first candidate to cut.
- Who uses it and how: one person (`solo`), a team, an organisation or the public; in which repositories; whether the users will read the plugin's code or just install it. Audience decides how much a hook may enforce (a personal plugin can be opinionated; an org plugin runs in repositories its author has never seen).

## Phase C: what kind of plugin it is

Single select, one or two allowed, because the kind predicts the component mix and the advice. The record names them `ecosystem`, `domain`, `workflow`, `integration`:

- ecosystem harness: tooling and conventions for one development ecosystem (Python with uv and ruff, TypeScript with pnpm, Terraform). Expect hooks that rewrite and gate, agents that run the toolchain, sometimes an LSP entry. Ask which ecosystem.
- domain knowledge: how this team does something (release process, review checklist, IaC layout). Expect skills that carry the procedure and references; few hooks.
- workflow or process: a sequence of steps across tools (triage, incident, onboarding). Expect a user-invocable skill per entry point and agents for the steps that need isolation.
- integration: wraps a service or API. Expect an MCP server and a skill that teaches when to call it.

Say which mix the kind predicts, then let the interview disagree with the prediction.

## Phase D: identity

One question with proposals pre-filled from B and C:

- name: non-empty kebab-case, no spaces, `@`, `:` or path separators, and not starting with `claude-` (the docs refuse reserved names; the validator rejects a `.` too). It prefixes every component the user sees (`/name:skill`, `name:agent`) and is the token before the marketplace in an install.
- five to eight keywords: the words a stranger would search, not the words in the name.
- a one-sentence description.
- license: an SPDX name or explicitly omitted. When declared it goes in the manifest and a `LICENSE` file should match; when omitted neither is rendered.
- `author` (a name; email and URL optional), `homepage` (must parse as a URL or Claude Code fails to load the plugin) and `repository`. `plugin validate` warns when the author is missing.
- values the user must supply at enable time (`userConfig`) and plugins this one needs (`dependencies`). Ask only when the plugin cannot work without them. `references/manifest.md` has the option fields and the dependency forms.

## Phase E: components, one kind at a time

Walk the kinds in this order. For each, first ask whether the plugin ships any (with one sentence on what the kind is for, from its reference), then one round per instance. Keep the rounds short; the builder skill asks the detailed questions later, so this interview records purpose, shape and the answers that decide the mechanism, not the implementation.

**Hooks** (`references/hooks.md`). When it runs, in plain words (before Claude runs a command, after an edit, when Claude says it is done, at session start); what it is for (prevent a failure mode, recover from one, inject context, track); what Claude should see afterwards. Plugin hooks run for every user of the plugin in every repository they open, so ask whether that is intended.

**MCP servers** (`references/mcp.md`). What Claude should be able to do that the shell cannot; local only or a network service; the tools, each with purpose and side effects (read-only, writes, destructive) and whether it should pause to ask the person; whether any tool acts on the user's repository (then it reads `CLAUDE_PROJECT_DIR` or takes a `root` parameter). Ask whether the plugin already ships an `.mcp.json` the new server must be merged into.

**LSP servers** (`references/lsp.md`). Only when the kind is an ecosystem harness or the user asks, and check first whether an official code intelligence plugin covers the language: which language server, which file extensions, and where users get the binary.

**Executables** (`references/executables.md`). A command-line tool that several skills or hooks call, shipped in `bin/`. Ask the name and what it does, and whether the users are on claude.ai or Cowork, which do not install a plugin with a `bin/` directory.

**Output styles** (`references/output-styles.md`). Only when the user wants Claude's voice or format changed. Ask the name, the change, whether coding instructions stay (`keep-coding-instructions`), and whether the style is forced on every user (`force-for-plugin`), which takes the choice from them.

**Skills** (`references/skills.md`). Name; what it does and when Claude should reach for it (the description is the whole trigger surface); model-invocable, human-only through `disable-model-invocation`, or both; whether it bundles scripts (then the interpreter goes in `allowed-tools` as a `Bash(...)` rule such as `Bash(uv *)`); which MCP tools it uses, if any (the server ships in the same plugin).

**Commands** (`references/commands.md`). A `/name ARGS` entry point. Say once that the plan renders it as a skill with `argument-hint`, not a `commands/` file, and ask whether any existing `commands/` files are being migrated.

**Agents** (`references/agents.md`). An agent does one thing very well with a specific tool set, and the plan should be able to say the one thing in a sentence. Ask: the one thing; the tools it needs and nothing more (`Read`, `Grep`, `Bash`, with `disallowedTools` for denials); when Claude should delegate to it; what it returns (shape, length); whether a cheap model is enough. An agent whose tool set equals the main session's, or whose job is "help with X", is not an agent; say so in phase F. A plugin agent cannot carry its own hooks or MCP servers, so those become plugin hooks and `.mcp.json` entries.

After each kind, show the accumulated component table (kind, name, purpose, builder) so the user can rename, merge or drop before the next kind.

## Phase F: challenge what is the wrong mechanism, then do what the user decides

Walk the table once. For each component, ask whether the mechanism matches the need, and when it does not, say so with the concrete reason from the reference and propose the fit:

- a hook that is a static blocklist ("never run X"): a `permissions.deny` rule such as `Bash(terraform apply *)` in the project `.claude/settings.json` does it without a process; a plugin cannot ship it, so it becomes an `outside_plugin` entry
- a hook that runs a procedure or carries judgement: a skill or an agent
- guidance that must be enforced: a hook, because guidance in a rule or skill cannot deny anything
- an agent with no distinct tool set or a job stated as "help with": a skill, or fold it into another agent
- an MCP server whose tools wrap commands Claude can run with the same arguments: a skill with `allowed-tools`
- a skill that must apply on every turn: an `outside_plugin` project rule file or `CLAUDE.md`, since the plugin cannot ship one
- an LSP entry where a `PostToolUse` hook running the checker on the edited file would do: a hook, unless live diagnostics are the point
- a command where Claude should also pick it up unprompted: a plain skill
- two components that solve the same failure: keep one

Discourage as hard as the reason warrants, once, then ask a single select per flagged component: switch to the proposed mechanism, or keep it as planned. The user's answer is the answer. Never switch, drop or reshape a component the user did not agree to change, and never write a sentence that reads as "you said X and I did Y"; the record stores the advice and the decision side by side (`advice: {mechanism, reason}`, `decision: as planned | switched`) so a later session sees the question was raised and settled, and the ready prompt tells the builder to build what was decided and not re-open it. When a switch lands outside what a plugin can ship (a permission in the team's settings, a project rule file, a CI step), record it under `outside_plugin` with the need, the mechanism and where it goes; `render` keeps it in PLAN.md and the publish session carries it. Then trace every remaining component back to the problem statement from phase B; a component with no trace is raised as a question, and the user decides whether it is cut or the problem statement grows.

## Phase G: layout

Show the tree the record implies, as `render` will draw it: the four plan files, then every file each component will own with the component's name beside it (`skills/<name>/SKILL.md`, `agents/<name>.md`, `hooks/hooks.json` plus `scripts/<name>.py`, `.mcp.json` and `mcp/<name>/`, `.lsp.json`, `bin/<name>`, `output-styles/<name>.md`). The quickest way is to write a draft `plugin-plan.json`, run `plugin render` into a scratch directory and paste the Layout section. Ask the user to confirm or rename; a change here is a change to the record, never a hand-edited tree, so the shell and the plan cannot disagree. `references/layout.md` has the full tree.

## Phase H: distribution

Single select: marketplace (a `.claude-plugin/marketplace.json` in a repository the team adds with `claude plugin marketplace add`, then `claude plugin install NAME@MARKETPLACE --scope project`; pin `sha` for anything with hooks or a server in it) or local (`claude --plugin-dir ./dir`, which loads the plugin for one session and installs nothing). Claude Code installs only `<plugin>@<marketplace>`, so sharing by repository means a marketplace in that repository. Record the install command in `distribution.install`; the record has no field for the marketplace's name or source, so without one the rendered text keeps `<marketplace>` and `<source>` placeholders. Say that after any edit a running session needs `/reload-plugins`, and that `version` in the manifest pins users until it changes. `references/marketplace.md` has the entry shape and the settings that live beside it.

## Phase I: the record and the shell

Write `plugin-plan.json` in the shape of `assets/plan.example.json`: `name`, `version`, `description`, `keywords`, `license` (an SPDX string or `null`), `author`, `homepage`, `repository`, optional `userConfig` and `dependencies`, `problem`, `audience` (`who` and `how`), `kinds`, `ecosystem`, `distribution` (`channel` and `install`), one entry per component with `kind` (one of the eight above), `name`, `purpose`, `status` (`planned`, or `built` from the inventory), `builder` (fixed per kind; `null` for lsp, executable and output-style), the `answers` gathered in E, the two or three `facts` from the kind's reference that constrain it, and `advice` plus `decision` when phase F raised something. Open questions the interview could not settle go in `open_questions` and are not silently resolved; routed needs go in `outside_plugin`.

Run `ai-engineer plugin validate plugin-plan.json` and show the output; errors fail it and `--strict` fails warnings too. Then, after one confirmation, `ai-engineer plugin render plugin-plan.json PLUGIN_DIR`. It writes `.claude-plugin/plugin.json` (from the identity), `README.md`, `PLAN.md`, `plugin-plan.json`, and the directories the planned components own, and nothing inside them. It refuses a target that already holds a manifest unless `--force` is given. `PLAN.md` has two top-level sections:

- `## Human` is the record a person reads: why, the interview decisions, the Layout tree, the component table with status and session number, then `### Phases`. Phases are in dependency order: 1 Foundation (hooks, output styles), 2 Capabilities (MCP servers, LSP servers, executables), 3 Skills and delegation (skills, commands, agents), 4 Verify and distribute (an install-and-verify session, then a publish session). Each phase lists its sessions, one per planned component, each with its ready-to-paste prompt in a fenced block. A prompt opens with the builder run under its plugin namespace, `/ai-engineer:create-skill ...`, and carries the plugin path, purpose, the files it owns, the answers as "everything you would otherwise ask me", the planning note when advice was given, the constraining facts, and the status flip to do when done. After the phases: what was routed outside the plugin and the open questions.
- `## Agent` is the context every builder session needs, one fact per line under stable keys (`plugin.*`, `phase.N`, `component.NAME.*` including `.session`, `.file`, `.reference`), so a session grepping `^component.NAME` gets everything about its component without reading the rest.

Check the shell with `claude plugin validate PLUGIN_DIR --strict`. For an existing plugin, `plugin render --force` rewrites only the plan files and manifest; component directories and files are never touched. Rendering does not write a `LICENSE` file; the plan names it as a step.

## Phase J: hand off

Say what to run next: Phase 1 first, and inside it the order the plan gives; MCP servers and executables before the skills that name them; agents last, because their discovery after loading is the thing to verify; then session 4.1 before anyone else installs it. Each builder session ends by flipping the component's status to `built` in both plan files and running `/reload-plugins`. Name what is unverified:

- whether `prompt` handlers in `hooks/hooks.json` run in a `-p` session, which the docs pages read for this skill do not say
- that `UserPromptExpansion` and `StopFailure` match older event names by name only
- where a plugin's stdio MCP server starts, which the docs do not state
- that `plugin validate` does not read `.lsp.json`, so an invalid LSP entry shows only in the `/plugin` Errors tab
- that the marketplace name and source are not in the record

Do not build any component in this session even if asked to "just do the first one"; say that the builder skill for it is one paste away and why the record should exist before the first piece does.
