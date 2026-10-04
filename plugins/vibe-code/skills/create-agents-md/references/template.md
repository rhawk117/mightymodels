# Output templates

## AGENTS.md skeleton

Sections in this order. Delete any section with nothing real to say; never pad. Target 150 lines or fewer in total.

```markdown
# <repo-name>: agent instructions

## Commands
<!-- verified only; prefix "(unverified)" where applicable; include flags -->
- Test: `uv run pytest -q`
- Lint: `uv run ruff check src tests`
- Typecheck: `uv run ty check src`
- Build: ...
- Run: ...

## Stack
<!-- exact versions and tools, one line each: "Python 3.12, uv, ruff, pytest" -->

## Layout
<!-- only non-obvious pointers: "API handlers live in src/api/handlers/" -->

## Conventions
<!-- only deviations from ecosystem defaults, each with its why -->
<!-- include the observed commit convention: "Conventional commits (feat/fix/chore), scope optional, matches git history" -->

## Boundaries
- Always: <e.g. run the Verification commands before finishing>
- Ask first: <e.g. dependency changes, schema migrations>
- Never: <e.g. edit src/*/generated/ and regenerate with `make codegen`>

## Verification
<!-- the exact commands an agent runs before declaring work done -->
```

A code example section is allowed only when observed style genuinely deviates from what a model produces by default: one real snippet from the repo, not an invented one.

## CLAUDE.md router

Write it when step 1 chose the import, or when a `CLAUDE.md` or `CLAUDE.local.md` is already on the path (Claude would otherwise skip `AGENTS.md`).

```markdown
@AGENTS.md

## Claude Code
<!-- Claude-specific rules only (e.g. "use plan mode for changes under src/billing/").
     Delete this section if there are none. -->
```

The `@AGENTS.md` import keeps `AGENTS.md` as the one file every tool shares, and Claude reads the imported file first, then the rest. Prefer it over a symlink: a symlink cannot hold Claude-specific additions, the Edit and Write tools refuse to write through it, and on Windows it needs Administrator privileges or Developer Mode. If there are no Claude-specific rules and nobody works on Windows, `ln -s AGENTS.md CLAUDE.md` is enough.

## Merge guidance (existing instruction files)

| From existing files | Disposition |
| --- | --- |
| Commands, validation steps | Migrate to AGENTS.md `## Commands` / `## Verification`; reconcile against explorer findings. CI wins conflicts |
| Real conventions, boundary rules ("never touch X", "ask before Y") | Migrate to `## Conventions` / `## Boundaries` |
| Claude-specific rules (plan-mode habits, tool quirks) | Keep in the `## Claude Code` section of `CLAUDE.md` |
| Personas, overview prose, linter duplicates, stale facts | Drop; list each dropped item and its reason when presenting the draft |

Existing `CLAUDE.md` with real content: migrate its keep-worthy rules, then replace the file body with the router (import first line). Existing `CLAUDE.local.md` and `.claude/rules/*.md`: leave them as they are. Existing cursor, windsurf and cline rules: mine them but leave the files untouched, because other tools may still read them, and say so to the user.
