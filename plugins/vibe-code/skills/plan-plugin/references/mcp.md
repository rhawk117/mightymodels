# MCP servers (`.mcp.json`)

Sources: Claude Code docs, plugins/components (MCP servers), plugins/manifest-reference (`mcpServers`, Environment variables). Builder: `create-mcp`.

## What it is

`.mcp.json` at the plugin root (with the leading dot) declares servers Claude Code starts or connects to when the plugin is enabled, in the same shape as a project `.mcp.json`. The `mcpServers` wrapper is optional; a server name may sit at the top level of the file. The manifest key `mcpServers` takes an inline map, a path to a JSON file or an array of those, and a manifest server with the same name as one in `.mcp.json` replaces it. The server's code is a convention: `create-mcp` keeps it in `mcp/<name>/` as a uv project, and Claude Code does not read that folder.

```json
{
  "mcpServers": {
    "repo-inspector": {
      "command": "uv",
      "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/mcp/repo-inspector", "repo-inspector"],
      "env": { "LOG_DIR": "${CLAUDE_PLUGIN_DATA}/logs" }
    }
  }
}
```

## Names

In `/mcp` the server is `plugin:<plugin>:<server>`. Its tools are `mcp__plugin_<plugin>_<server>__<tool>`, the name to use in permission rules and hook matchers. A matcher on the server name alone never fires.

## Runtime facts

- `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}` and `${CLAUDE_PROJECT_DIR}` are substituted in `command`, `args` and `env`; no quoting is needed in `args`.
- `claude plugin validate` checks `.mcp.json` and reports an entry Claude Code would drop at load time as an error (Claude Code v2.1.281 or later), plus a `${user_config.KEY}` reference to an undeclared option and a remote `url` that is not a valid absolute URL. It warns on a plain-HTTP or unencrypted WebSocket URL to a non-loopback host.
- `/reload-plugins` keeps the connection of a server whose configuration is unchanged and reconnects one that changed.
- A local stdio server runs in Claude Code and in a Cowork session on the user's machine, but not on claude.ai; a remote server referenced by its `https://` URL reaches claude.ai and Cowork as a connector.
- The docs do not say where a plugin stdio server starts. A server that acts on the user's repository should read `CLAUDE_PROJECT_DIR` or take a `root` parameter rather than guess.
- An agent file cannot declare servers (`mcpServers` is ignored in a plugin agent); all servers go in `.mcp.json`.

## When an MCP server is the right mechanism

Claude needs something the shell cannot give it: a network service, an API with auth, structured results, state across calls, a confirmation step. Not: wrapping a command Claude can already run with the same arguments (a skill with `allowed-tools`), or exposing a repo-local script (a skill plus the interpreter in `allowed-tools`).

## Plan snippet

- `.mcp.json` at the plugin root launching `uv run --project ${CLAUDE_PLUGIN_ROOT}/mcp/<name> <name>`
- appears as `plugin:<plugin>:<name>` in `/mcp`; tools are `mcp__plugin_<plugin>_<name>__<tool>`
- repository-acting tools use `CLAUDE_PROJECT_DIR` or a `root` parameter
- the skill that teaches when to call the tools ships in the same plugin
