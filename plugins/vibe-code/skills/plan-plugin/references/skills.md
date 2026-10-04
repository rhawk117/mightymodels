# Skills (`skills/<name>/SKILL.md`)

Sources: Claude Code docs, skills (frontmatter table, plugin skill names), plugins/components (Skills). Builder: `create-skill`.

## What it is

A directory with a `SKILL.md` (YAML frontmatter plus Markdown body) and optional supporting files. Claude reads every skill's `description` and loads the body when the request matches; the user can also run it by name. In a plugin it runs as `/<plugin>:<directory>`; a frontmatter `name` replaces the last segment and the prefix stays.

## Frontmatter

| field | meaning |
| --- | --- |
| `name` | optional; defaults to the directory name |
| `description` | what the skill does and when to use it; the trigger surface. `description` and `when_to_use` together are cut at 1,536 characters in the skill listing, so put the key use case first |
| `when_to_use` | extra trigger phrases, appended to `description` |
| `argument-hint` | text shown at autocomplete, such as `[issue-number]` |
| `disable-model-invocation` | `true` stops Claude loading it automatically; use for workflows triggered by hand with `/name`; default `false` |
| `user-invocable` | `false` hides it from the `/` menu and Claude alone invokes it; default `true` |
| `allowed-tools` | tools Claude can use without asking during the turn that invokes the skill; a space- or comma-separated string or a YAML list; the grant clears at the next message |
| `license` | accepted, not acted on |

There is no skill-level MCP field: the body names the MCP tools it needs and relies on a server the plugin declares in `.mcp.json`.

## Plugin facts

- A plugin skill and a skill at any other location both load, because plugin skills are namespaced. Do not plan around one shadowing the other.
- `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}` and `${CLAUDE_PROJECT_DIR}` are substituted in skill content.
- Instructions that must reach Claude go in a skill: a `CLAUDE.md` at the plugin root is not loaded.
- A skill that must hold every time (blocking edits to protected files) belongs in a hook, not a skill.
- `allowed-tools` advice for the user's plugin: write rules in permission syntax such as `Bash(uv *)` or `Bash(terraform validate *)`. A skill that runs bundled scripts needs its interpreter pre-approved. The plan may advise this; this toolkit's own skills set none.

## When a skill is the right mechanism

A procedure with judgement in it, references Claude should read on demand, a workflow entry point (`/name`), or the teaching half of an MCP server (when to call which tool). Not: guidance that must be always on (project rule or `CLAUDE.md`, outside the plugin), something that must be enforced (hook or permission), a job that needs a different tool set from the main agent (agent).

## Plan snippet

- ships in `skills/<name>/`; runs as `/<plugin>:<name>`
- the description is the whole trigger surface; `disable-model-invocation: true` keeps Claude from loading it
- bundled scripts need the interpreter in `allowed-tools`, written as `Bash(...)` rules
- names MCP tools in the body; the server ships in the plugin's `.mcp.json`
