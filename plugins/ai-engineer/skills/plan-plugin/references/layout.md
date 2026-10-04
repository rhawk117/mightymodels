# Plugin layout

Sources: Claude Code docs, plugins/manifest-reference (Standard layout), plugins/components, plugins/loading, plugins/cli-reference. Anything marked convention is this toolkit's habit, not something Claude Code reads.

## The tree a plugin can ship

```
NAME/
  .claude-plugin/plugin.json     manifest; optional, only `name` is required
  README.md                      convention; for people, not loaded by Claude Code
  LICENSE                        convention; present when plugin.json declares a license
  skills/<name>/SKILL.md         skills; also `scripts/`, `references/`, `assets/` beside it
  agents/<name>.md               agents; subfolders become part of the name
  hooks/hooks.json               hooks, under a top-level "hooks" key
  scripts/<name>.py              convention: scripts the hooks call through ${CLAUDE_PLUGIN_ROOT}
  .mcp.json                      MCP servers (leading dot)
  mcp/<name>/                    convention: server code; Claude Code does not read the folder
  .lsp.json                      LSP servers, server name straight to its config
  bin/<name>                     executables on the Bash tool's PATH while the plugin is enabled
  output-styles/<name>.md        output styles
  commands/<name>.md             legacy command files; a skill replaces them
```

The manifest lives in `.claude-plugin/`; every other file sits at the plugin root, never inside `.claude-plugin/`. Claude Code does not load a `CLAUDE.md` at the plugin root and `claude plugin validate` warns when it finds one, so instructions that must reach Claude go in a skill. The kinds this toolkit plans are the eight in `SKILL.md`; the standard layout has more directories (workflows, themes, monitors, a plugin `settings.json`) that the plan does not cover.

`ai-engineer plugin render` draws this tree for the components in the record and creates the directory each planned component owns: `skills/<name>/`, `hooks/`, `agents/`, `mcp/<name>/`, `bin/`, `output-styles/`. The LSP kind creates none because `.lsp.json` is a file. Nothing is written inside those directories; the builder sessions fill them.

## Names and namespacing

Claude Code namespaces every component under the plugin name. A skill is `/<plugin>:<directory>`, an agent `reviewer` in `deploy-tools` is `deploy-tools:reviewer`, an agent in a subfolder adds a segment (`agents/review/security.md` is `my-plugin:review:security`), and a plugin MCP server shows in `/mcp` as `plugin:<plugin>:<server>` with tools named `mcp__plugin_<plugin>_<server>__<tool>`.

## Precedence and collisions, per kind

| kind | what the docs say | consequence |
| --- | --- | --- |
| skills | plugin skills are namespaced as `/plugin-name:skill-name`, so they load beside a same-named skill at any other location | no collision; do not plan around shadowing |
| agents | plugin agents carry the plugin prefix, so `reviewer` and `my-plugin:reviewer` are two subagents | no collision |
| MCP servers | the server is `plugin:<plugin>:<server>`; a manifest server with the same name as one in `.mcp.json` replaces it | collisions happen only inside one plugin |
| hooks | hook entries merge across levels rather than replacing each other | the same hook at two levels runs twice |
| LSP servers | when two enabled servers claim an extension, the first registered handles it | one server per extension; the `/plugin` Errors tab warns about the other |
| commands | a skill and a command in `commands/` are both loaded | prefer a skill |

## Load, reload, cache

- `claude --plugin-dir ./NAME` loads a directory (or a `.zip`) for one session without installing it; edit the files and run `/reload-plugins` in the running session. The plugin appears as `<name>@inline` in `claude plugin list` when the same flag precedes the subcommand.
- A marketplace install copies the plugin into `cache/<marketplace>/<plugin>/<version>/`; `${CLAUDE_PLUGIN_ROOT}` points at that version directory and changes with every version, so durable data goes in `${CLAUDE_PLUGIN_DATA}`. Files outside the plugin directory are not copied. A relative-path plugin in a marketplace added from a local directory loads in place instead.
- `version` in `plugin.json` pins users to that version until you change it, so bump it on every release.
- `CLAUDE_CODE_PLUGIN_CACHE_DIR` moves the plugins root (marketplaces and the cache live under it); point it at an empty directory to test an install from scratch.

## Checking a plugin

`claude plugin validate <dir> --strict` is the authoritative check of the manifest; it also checks each MCP server entry in `.mcp.json` and finds agent files whose frontmatter does not parse. It does not read `.lsp.json`; an invalid LSP entry skips the whole file at load and the `/plugin` Errors tab shows it. After loading, `/mcp` lists servers, `/hooks` lists hook configurations and `/reload-plugins` prints a summary line of what loaded.
