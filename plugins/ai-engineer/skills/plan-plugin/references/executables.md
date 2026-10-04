# Executables (`bin/<name>`)

Sources: Claude Code docs, plugins/components (Executables), plugins/manifest-reference (Standard layout). No builder skill: the plan records the file and its session is a short manual one.

## What it is

Files in `bin/` at the plugin root are on the `PATH` of the Bash tool's shell while the plugin is enabled, so Claude, or a skill's instructions, can run them as bare commands without the user installing anything. This toolkit's own plugin ships `bin/ai-engineer` this way.

```bash
#!/bin/bash
echo "hello from my-plugin"
```

Make the file executable (`chmod +x bin/<name>`) and load the plugin; asking Claude to run the command shows the script's output in the Bash tool result.

## Runtime facts

- Plugin `bin/` directories come after the user's own `PATH` entries, so an executable cannot shadow `git`, `ls` or another system command; give it a distinctive name.
- claude.ai and Cowork do not install a plugin that has a top-level `bin/` directory, including one distributed through claude.ai organization settings. Ask in the interview whether the plugin's users are on those surfaces and say so in the plan.

## When an executable is the right mechanism

A tool several skills or hooks call, so the plugin ships it once instead of copying a script into each skill. A hook script that only one hook calls stays in `scripts/` (convention) and is called through `${CLAUDE_PLUGIN_ROOT}`. Phase 2 of the plan builds executables before the skills that call them, so those skills can name the real command.

## Plan snippet

- ships in `bin/<name>`, executable bit set; on the Bash tool's `PATH` while the plugin is enabled
- sits after the user's own `PATH`; cannot shadow a system command
- a plugin with `bin/` is not installed by claude.ai or Cowork
