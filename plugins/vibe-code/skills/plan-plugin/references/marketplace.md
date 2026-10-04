# Distribution and `marketplace.json`

Sources: Claude Code docs, plugins/install, plugins/cli-reference, plugins/marketplace-reference (Plugin entries, plugin sources, `sha`), plugins/loading (enabledPlugins sources), settings-reference. Claude Code installs a plugin as `<plugin>@<marketplace>`.

## Channels

| channel | commands | when |
| --- | --- | --- |
| marketplace | `claude plugin marketplace add OWNER/REPO` then `claude plugin install NAME@MARKETPLACE --scope project` | anything shared with a team or org |
| local | `claude --plugin-dir ./NAME` loads it for one session and installs nothing | personal use and every builder session's smoke test |

A marketplace is a catalog of plugins, and Claude Code has to know about the marketplace before you can install from it. The install target is `<plugin>@<marketplace>`; the session form of `/plugin install` reports a marketplace-not-found error for a path, URL or `owner/repo`. A plugin shared by repository is therefore shared through a marketplace in that repository, and the record's `distribution.channel` is `marketplace` or `local`.

`--scope` takes `user`, `project` or `local` and names the settings file written; it defaults to `user`. `marketplace add` takes `owner/repo`, `owner/repo#ref`, a git URL, a hosted `marketplace.json` URL or a local path, and its own `--scope` defaults to `user` too. `project` scope writes `.claude/settings.json`, which everyone who clones the repository shares.

## `.claude-plugin/marketplace.json`

Save the file at `.claude-plugin/marketplace.json` in the marketplace repository. `name`, `owner` and `plugins` are required; `owner` needs `name`.

```json
{
  "name": "platform-tools",
  "owner": { "name": "Platform team", "email": "platform@example.com" },
  "plugins": [
    {
      "name": "py-harness",
      "source": {
        "source": "github",
        "repo": "example/py-harness",
        "ref": "v0.1.0",
        "sha": "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"
      },
      "description": "Python project harness for Claude Code sessions",
      "version": "0.1.0"
    }
  ]
}
```

An entry needs `name` and `source`. A `source` is a relative path string (for a plugin in the marketplace repository itself, starting with `./`) or an object: `github` (`repo`, `ref`, `sha`), `url` (`url`, `ref`, `sha`), `git-subdir` (`url`, `path`, `ref`, `sha`) and others the reference lists. An entry also takes the manifest fields such as `description` and `version`, and `strict` (default `true`: `plugin.json` is the definitive source for components). An unknown key is ignored at load and `claude plugin validate` warns about it. The marketplace `name` may not be one of the reserved names (the reference lists them).

## Pin `sha`

`sha` is a full 40-character lowercase commit SHA. When both `ref` and `sha` are set, Claude Code checks out `sha`. Pin it for a plugin that ships hooks or an MCP server: a `ref` alone is a moving target, and those components run code on every user's machine.

## Settings that live beside the plugin

These go in settings files, not in the plugin, and the publish session carries them as `outside_plugin` items:

- `enabledPlugins` (`"name@marketplace": true`) can be set in any of six sources, lowest to highest precedence: `--add-dir`, `user` (`~/.claude/settings.json`), `project` (`.claude/settings.json`), `local` (`.claude/settings.local.json`), `flag` and `managed`; the highest-precedence source that mentions the id wins, and `managed` cannot be overridden.
- `extraKnownMarketplaces` registers marketplaces for a repository or organization; `strictKnownMarketplaces` (managed settings) allow-lists the sources users may add.
- Permissions: `permissions.allow` and `permissions.deny` in the project `.claude/settings.json`. A plugin's own `settings.json` or manifest `settings` key keeps only `agent` and `subagentStatusLine`, so permissions can never ship in a plugin.

## Plan snippet

- distribution: marketplace `NAME@MARKETPLACE`, with `sha` pinned for hooks or servers, or local `claude --plugin-dir ./NAME`; record the install line
- the marketplace file is `.claude-plugin/marketplace.json` with `name`, `owner` and `plugins`
- permissions and policy live in `.claude/settings.json` or managed settings, not in the plugin
