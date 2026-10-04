# Agents (`agents/<name>.md`)

Sources: Claude Code docs, plugins/components (Agents), sub-agents (frontmatter table, plugin subagents, invoke explicitly). Builder: `create-subagent`.

## What it is

A Markdown file under `agents/` whose frontmatter names the agent and says when to use it and whose body is its system prompt. It is a separate assistant with its own context window that Claude delegates a task to. An agent does one thing with a specific tool set; the plan should be able to say the one thing in a sentence. Older plans called this kind a worker; `plugin validate` rejects `worker` and says to use `agent`.

## Names

`<plugin>:<name>`, where `<name>` is the frontmatter name or the file name. A subfolder adds a segment (`agents/review/security.md` is `my-plugin:review:security`). The user invokes it with `@agent-<plugin>:<name>`, and enabled plugin agents appear in the typeahead under their scoped name. The `agents` manifest key replaces the `agents/` scan.

## Frontmatter in a plugin agent

| supported | meaning |
| --- | --- |
| `name`, `description` | `description` drives delegation |
| `tools` | allow-list, a comma-separated string such as `Read, Grep, Bash` or a YAML list; omitted means every tool a subagent inherits |
| `disallowedTools` | denials removed from the inherited or listed tools |
| `model` | `sonnet`, `opus`, `haiku`, a full model ID, or `inherit` |
| `effort`, `maxTurns`, `skills`, `memory`, `background`, `omitClaudeMd`, `color` | see the sub-agents page |
| `isolation` | only valid value is `"worktree"` |

Ignored in a plugin agent: `permissionMode`, `hooks`, `mcpServers` and `initialPrompt`. An agent file cannot add hooks or MCP servers by itself, so the plugin ships them as `hooks/hooks.json` and `.mcp.json`; a need for permissions goes in `outside_plugin` (project `.claude/settings.json`). Frontmatter that does not parse still loads the agent with every field ignored and the description `Agent from <plugin> plugin`; `plugin validate` finds these files.

## Runtime facts

- Plugin agents have the lowest priority of the agent locations, and carry the plugin prefix, so `reviewer` and `my-plugin:reviewer` are two agents.
- Hook matchers for `SubagentStart` and `SubagentStop` use the scoped name, written as `^my-plugin:db-agent$` to anchor it.

## When an agent is the right mechanism

A job with a tool set narrower than the main agent's, a result that should come back short and structured, work that should not fill the main context, or a step where a cheaper model is enough. Not: "help with X" (a skill), a job whose tool set equals the main agent's (a skill or nothing), a fixed check a hook can run without a model.

## Plan snippet

- ships in `agents/<name>.md`; registers as `<plugin>:<name>`; addressed as `@agent-<plugin>:<name>`
- `tools` is the hard limit on what it can touch; `hooks`, `mcpServers` and `permissionMode` are ignored in a plugin agent
- verify discovery in the typeahead after loading the plugin
