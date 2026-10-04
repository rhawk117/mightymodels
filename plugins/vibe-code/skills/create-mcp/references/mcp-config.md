# Claude Code MCP configuration facts

Snapshot 2026-10-03 of https://code.claude.com/docs/en/mcp and https://code.claude.com/docs/en/plugins/components. A statement marked unverified is not in that snapshot.

## Where a server can be configured

| scope   | file                                                                           | who sees it                      | written by                                   |
| ------- | ------------------------------------------------------------------------------ | -------------------------------- | -------------------------------------------- |
| local   | `~/.claude.json`, under the project's path                                     | you, in this project only        | `claude mcp add --scope local` (the default) |
| project | `.mcp.json` at the repository root                                             | everyone who clones the repo     | `claude mcp add --scope project`, or by hand |
| user    | `~/.claude.json`                                                               | you, in every project            | `claude mcp add --scope user`                |
| plugin  | `.mcp.json` at the plugin root, or the `mcpServers` key of `.claude-plugin/plugin.json` | wherever the plugin is enabled | by hand                                      |

A local server is stored under the project's path in `~/.claude.json`, so it does not appear in your other projects. `.mcp.json` is the shared file: check it in. Claude Code asks for approval before it uses a project server (see "Project approval" below).

When the same server is defined in more than one place, Claude Code connects to it once, using the entry from the highest-precedence source. Order, highest first: local, project, user, plugin-provided, claude.ai connectors. The whole entry is used; fields are not merged across scopes. `claude -p --mcp-config <file-or-json>` adds servers for one run.

## Plugin servers

A plugin declares servers in `.mcp.json` at the plugin root, in the same shape as a project `.mcp.json`. There is no `$schema` key. The `mcpServers` wrapper may be omitted in a plugin file, and a project file is documented only with the wrapper, so generate the wrapper in both.

Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` in `command`, `args` and `env`, and exports both to the server process. `${CLAUDE_PROJECT_DIR}` is substituted in a plugin file without a default. The plugin shape this skill generates:

```json
{
  "mcpServers": {
    "NAME": {
      "command": "uv",
      "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/mcp/NAME", "NAME"]
    }
  }
}
```

Servers of enabled plugins connect at session start and when a plugin is enabled or reloaded. A reload keeps the live connection of a server whose configuration did not change. In `/mcp` the server appears as `plugin:<plugin>:<server>`. `claude plugin validate --strict` reads the plugin `.mcp.json` and reports a server entry that Claude Code would drop at load time as an error.

Install step: no install step exists. A `SessionStart` hook in `hooks/hooks.json` can build an environment into `${CLAUDE_PLUGIN_DATA}`, a directory that survives plugin updates and is documented for `node_modules`, virtual environments and caches. Pointing `uv` at that directory has not been tried here (unverified). `uv` must be on the `PATH` of the session.

## Entry shape

| key                                | where                             | meaning                                                                      |
| ---------------------------------- | --------------------------------- | ---------------------------------------------------------------------------- |
| `type`                             | every entry                       | `stdio`, `http`, `sse` or `ws`; `streamable-http` is an alias for `http`     |
| `command`, `args`, `env`           | `stdio`                           | what to launch                                                               |
| `url`, `headers`, `headersHelper`  | `http`, `sse`, `ws`               | where to connect and how to authenticate                                     |
| `oauth`                            | `http`                            | pre-configured OAuth fields                                                  |
| `timeout`                          | every entry                       | milliseconds a single tool call may run                                      |
| `alwaysLoad`                       | every entry                       | load this server's tools at session start instead of deferring them          |

An entry with a `url` and no `type` is a configuration error: Claude Code reads it as stdio and skips it. `local` is not a documented `type`. `sse` is deprecated; prefer `http`.

There is no `tools` key. To narrow what the model may call, write permission rules in the `permissions.allow` and `permissions.deny` lists of a settings file: `mcp__NAME` (every tool of the server), `mcp__NAME__*` (the wildcard form, the same set) or `mcp__NAME__tool`. A tool reaches the model under the name `mcp__NAME__tool`; for a plugin-bundled server the name carries the plugin: `mcp__plugin_<plugin>_<server>__<tool>`.

## Timeouts

- Startup: the `MCP_TIMEOUT` environment variable, in milliseconds. `MCP_TIMEOUT=10000 claude` sets ten seconds.
- One tool call: the `timeout` key on the entry, for example `"timeout": 600000`. It is a hard limit per call and progress notifications do not extend it. A value below 1000 is ignored.

The generated project shape sets `timeout` to 120000 because the first `uv run` in a fresh checkout builds the environment.

## Environment variables in an entry

`${VAR}` and `${VAR:-default}` expand in `command`, `args`, `env`, `url` and `headers`. A bare `$VAR` is not in the supported syntax, so write the braces.

If a referenced variable is unset and has no default, the config still loads: Claude Code warns in `claude mcp list` and keeps the unexpanded `${VAR}` text. In a remote server's `url` and `headers`, credential variables such as `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `AWS_BEARER_TOKEN_BEDROCK`, `HTTPS_PROXY` and `NPM_TOKEN` read as empty, even with a default; copy the value into a variable with a name of your own and reference that. `ai-engineer mcp validate` warns about each of these cases.

`CLAUDE_PROJECT_DIR` is set in the server's own environment, not in Claude Code's. Referenced through `${...}` in a project or user entry it needs a default, as in `${CLAUDE_PROJECT_DIR:-.}`.

## Where a server finds the project

Claude Code sets `CLAUDE_PROJECT_DIR` in the spawned server's environment to the project root; read it as `os.environ["CLAUDE_PROJECT_DIR"]`. It does not change when working directories are added mid-session. The directory a stdio server starts in is not documented (unverified), so the server must not depend on it.

A server that limits itself to a set of allowed directories should implement `roots/list`. Claude Code answers with the launch directory plus every directory added with `--add-dir`, `/add-dir` or the `additionalDirectories` setting, and sends `notifications/roots/list_changed` when that set changes. This needs Claude Code v2.1.203 or later; before that `roots/list` returned only the launch directory.

## Project approval

In an interactive session Claude Code asks for approval before it uses a server from a project `.mcp.json`. `claude mcp reset-project-choices` resets the choices. `claude -p` loads project servers without asking. To block one, add it to `disabledMcpjsonServers` in a settings file, or start with `--strict-mcp-config` so only `--mcp-config` servers load. Until it is approved, `claude mcp list` shows the server as pending approval.

## Remote servers

A remote entry has `"type": "http"`, `url`, optional `headers` (values may use `${VAR}`), `oauth` and `headersHelper`. Sign in with `claude mcp login NAME` or `/mcp`. In a `claude -p` run there is no `/mcp` panel, so Claude Code cannot run the OAuth flow. This skill does not generate authentication.

## Permissions in scripted runs

`claude -p --allowedTools "mcp__NAME__tool"` (or `mcp__NAME` for the whole server) lets a call run without a prompt; `--disallowedTools` adds deny rules. Deny rules are checked first, then ask, then allow.

## The uv entrypoint

`[project.scripts] NAME = "PKG.cli:main"` makes `uv run NAME` start the server after `uv sync`. The generated configs launch `uv run --project <project-dir> NAME`, which resolves the environment from the project's lockfile. `ai-engineer mcp validate --check-command` runs `uv run --project ... NAME --help` to prove the entrypoint resolves before a session depends on it.
