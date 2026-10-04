# Commands (a skill with `argument-hint`)

Sources: Claude Code docs, plugins/components (Commands), skills (frontmatter table). Builder: `create-skill`.

## What the plan does with the kind

`command` is a plan kind for a component the user runs by name with an argument. `ai-engineer plugin render` writes it as `skills/<name>/SKILL.md`, a user-invocable skill with `argument-hint`, and its builder is `create-skill`. It does not write a file under `commands/`.

Why: the docs call commands the older format and say skills supersede them for new work, since a skill runs by name the same way and can also carry supporting files in its directory. `commands/<file>.md` still works (it becomes `/<plugin>:<file>`, a subfolder adds a segment, and the frontmatter is the same as a skill's) and is for files being moved over from `.claude/commands/`. If the user is migrating such files, say so in the plan as an open question; the render will not create them, and `ai-engineer plugin inventory` records an existing `commands/*.md` file as a command.

## Frontmatter the builder session sets

`argument-hint` (shown at autocomplete), `description`, and `disable-model-invocation: true` when only a human should trigger it, as for a release cut. See `references/skills.md`.

## When to record a command and when a skill

Record a command when the user's picture is "type `/name ARGS`". Record a skill when Claude should also reach for it on its own. Both end up the same file; the kind decides the opener the builder gets and the way the plan reads. Say this once in the interview.

## Plan snippet

- ships as `skills/<name>/SKILL.md` with `argument-hint`; runs as `/<plugin>:<name>`
- not a `commands/` file; `commands/` is the legacy format
