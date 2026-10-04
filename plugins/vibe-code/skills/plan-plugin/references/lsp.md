# LSP servers (`.lsp.json`)

Sources: Claude Code docs, plugins/components (LSP servers), plugins/code-intelligence. No builder skill: the plan records the entry and its session is a short manual one.

## What it is

An LSP server gives Claude diagnostics and code navigation for a language. If an official code intelligence plugin already covers the language, install that instead of writing one. Otherwise declare the server in `.lsp.json` at the plugin root. The file maps each server name directly to its configuration, with no wrapper object.

```json
{
  "pyright": {
    "command": "pyright-langserver",
    "args": ["--stdio"],
    "extensionToLanguage": { ".py": "python", ".pyi": "python" }
  }
}
```

`command` is the binary's name with its arguments in `args`. `extensionToLanguage` needs at least one extension and each starts with `.`. The `lspServers` manifest key takes the same map inline, a path or an array, adds to `.lsp.json`, and a manifest server with the same name replaces the file's. Other fields exist (`transport`, timeouts, restarts); see the manifest reference page for `lspServers`. An unknown key inside an LSP config is an error and the plugin does not load.

## Runtime facts

- The plugin configures the connection but does not install the binary; Claude Code starts `command` by name from the user's `PATH`. A missing binary logs `LSP server <name> failed to start` under `claude --debug`. The plan records where users get the binary.
- Each file extension gets one server. When two enabled servers claim one, the first registered handles it and the `/plugin` Errors tab warns about the other.
- `claude plugin validate` does not read `.lsp.json`. When any entry is invalid the whole file is skipped at load and `Invalid LSP server config for ".lsp.json"` shows in the Errors tab.
- The server must write logs to stderr; stdout carries protocol messages only.

## When an LSP entry is the right mechanism

An ecosystem plugin whose users edit files Claude cannot check without a compiler or type checker (Terraform, Go, Rust, TypeScript). Not: a project that already runs the checker through a `PostToolUse` hook, unless live diagnostics are the point.

## Plan snippet

- ships in `.lsp.json`; `extensionToLanguage` is required; no wrapper object
- the binary must be on the user's `PATH`; record where it comes from
- one server per extension; a conflict shows in the `/plugin` Errors tab
