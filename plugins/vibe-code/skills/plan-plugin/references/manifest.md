# `.claude-plugin/plugin.json`, README and LICENSE

Sources: Claude Code docs, plugins/manifest-reference (Fields, `name`, `dependencies`, User configuration, Unrecognized fields, Path rules). The record fields below are what `vibe-code plugin render` copies into the manifest.

## What the manifest is

The manifest is optional; `name` is the only required key. Save it at `.claude-plugin/plugin.json`. Without one, Claude Code names the plugin after its directory under `--plugin-dir`. This toolkit always writes one so the plan, version and metadata have a home.

```json
{
  "name": "py-harness",
  "version": "0.1.0",
  "description": "Python project harness: uv, ruff, ty and pytest conventions for Claude Code sessions.",
  "author": { "name": "Platform team", "email": "platform@example.com" },
  "homepage": "https://example.com/platform/py-harness",
  "repository": "https://example.com/platform/py-harness.git",
  "license": "MIT",
  "keywords": ["python", "uv", "ruff", "ty", "pytest"]
}
```

| key | rule from the docs | record field |
| --- | --- | --- |
| `name` | non-empty, no spaces, `@`, `:`, path separators or control characters; use kebab-case; every component is namespaced under it | `name` |
| `version` | a string, not checked against semver; setting it keeps users on that version until you change it | `version` |
| `description` | short explanation of what the plugin provides | `description` |
| `author` | object: `name` required, `email` and `url` optional; `claude plugin validate` warns when `author` is missing | `author` |
| `homepage` | documentation URL; must parse as a URL or the plugin fails to load | `homepage` |
| `repository` | source repository URL; not validated | `repository` |
| `license` | SPDX identifier such as `MIT` or `Apache-2.0` | `license` |
| `keywords` | discovery tags | `keywords` |
| `userConfig` | values Claude Code prompts for when the plugin is enabled | `userConfig` |
| `dependencies` | plugins that must be enabled for this one to work | `dependencies` |

`$schema` is accepted for editor autocomplete and ignored at load; the render writes none. An unrecognized top-level key is stripped and `claude plugin validate` warns about it (a failure under `--strict`). Other keys exist (component path keys such as `skills`, `agents`, `hooks`, `mcpServers`, `lspServers`, `outputStyles`) and each path must start with `./`, resolve inside the plugin root and exist; the plan uses the default locations and needs none of them.

## Reserved and refused names

`claude plugin validate` fails a name that starts with `claude-`, `anthropic-`, `anthropics-` or `cc-plugin-`, or equals `claude`, `anthropic`, `anthropics`, `claude-code` or `claude-mods`, and warns when one of those words appears as a whole word elsewhere. `plugin validate` of this CLI rejects a `claude-` prefix, any `.`, space, `@`, `:` or path separator, and anything that is not lowercase kebab-case.

## User configuration

`userConfig` maps a key (letters, digits and underscores, not starting with a digit) to an option. Each option is a strict object, so an unknown key fails validation:

| field | meaning |
| --- | --- |
| `type` (required) | `string`, `number`, `boolean`, `directory` or `file` |
| `title` (required) | label in the configuration dialog |
| `description` (required) | help text beneath the field |
| `required`, `default`, `options`, `multiple`, `sensitive`, `min`, `max` | optional; `sensitive: true` masks input and stores the value in secure storage |

A component reads a saved value as `${user_config.KEY}` (MCP and LSP config, exec-form hook `args`, skill and agent content) or as the `CLAUDE_PLUGIN_OPTION_<KEY>` environment variable in hook processes. Shell-form hook commands reject `${user_config.*}`. `plugin validate` checks that each option has `type`, `title` and `description`. Ask for a value only when the plugin cannot work without the user's own endpoint, token or path; every option is a dialog the user meets at enable time. `options` makes a plugin fail to load on Claude Code before v2.1.271.

## Dependencies

`dependencies` is an array whose entries are `"name"`, `"name@marketplace"` or `{ "name": "...", "marketplace": "...", "version": "..." }`; a bare name resolves against the plugin's own marketplace. Record one only when the plugin's skills or hooks call something another plugin ships.

## README and LICENSE

Claude Code loads neither. The README is for the person deciding whether to install: the problem the plugin solves, who it is for, the install lines, what it ships, and what it changes in a session (a hook runs for every user of the plugin, so say so). `vibe-code plugin render` writes one from the record. The record's `license` is an SPDX string or `null`; when it is `null` the manifest omits the key and no LICENSE file is planned. A declared license needs a LICENSE file whose text matches (convention; `render` does not write it).

## Plan snippet (facts a manifest component carries)

- the manifest is `.claude-plugin/plugin.json`; only `name` is required; an unknown top-level key is stripped with a validate warning
- `name` namespaces every component and is the install token before the marketplace name
- bump `version` on every release; setting it pins users until it changes
