# Output styles (`output-styles/<name>.md`)

Sources: Claude Code docs, plugins/components (Themes and output styles), output-styles (frontmatter table). No builder skill: the plan records the file and its session is a short manual one.

## What it is

A Markdown file that changes how Claude formats and phrases replies: the body is the style's instructions. Save each style as `output-styles/<name>.md`; it appears in `/output-style` as `<plugin>:<name>`. The `outputStyles` manifest key replaces the `output-styles/` scan.

```markdown
---
name: terse
description: Answer in as few words as possible
keep-coding-instructions: true
---

Keep every reply short. Skip preambles and summaries.
```

| frontmatter | meaning |
| --- | --- |
| `name` | defaults to the file name |
| `description` | shown in the `/config` picker |
| `keep-coding-instructions` | `true` keeps Claude Code's built-in software engineering instructions beside the style; default `false`, which leaves them out |
| `force-for-plugin` | plugin styles only: `true` applies the style whenever the plugin is enabled and overrides the user's `outputStyle` setting; if several enabled plugins set it, the first loaded wins; default `false` |

## When an output style is the right mechanism

The user wants Claude's voice or format changed (terse, tutorial, report-shaped), not its behavior. A style that must hold for coding work sets `keep-coding-instructions: true`; one for a non-coding plugin leaves it out. `force-for-plugin` takes the choice away from the user, so ask before planning it. Not: a convention about code (project rule file, outside the plugin) and not an enforcement (hook).

## Plan snippet

- ships in `output-styles/<name>.md`; appears as `<plugin>:<name>` in `/output-style`
- `keep-coding-instructions: true` when the style should still code the same way
- `force-for-plugin: true` overrides the user's own style choice; plan it only when asked
