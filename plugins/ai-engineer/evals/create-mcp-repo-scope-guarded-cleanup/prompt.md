---
description: Project-scope MCP server reachable over stdio and HTTP, with a destructive tool that asks before deleting.
expected_outcome: A uv project under mcp/repo-janitor with a transport flag, a confirming remove_junk, tests driving the confirmation, a project .mcp.json with a raised timeout, and a validator pass.
tags: [create-mcp]
runs: 1
max_turns: 80
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Bash, Write, Edit]
---

I want an MCP server for this repo (fixtures/repo) that Claude Code uses to clean up build junk safely: list what would be removed, and actually remove it only after asking me.

Everything you'd otherwise ask me: project scope, committed config; server name repo-janitor. It should work both when Claude Code launches it locally and as a service on our CI box, so both. The server finds the project root through the environment variable Claude Code sets for it. Problem: Claude runs `rm -rf` on guesses. Tools: list_junk (input: patterns list[str] with default like __pycache__, .pytest_cache, dist; output: paths list[str]; read-only) and remove_junk (input: paths list[str]; output: removed list[str] and skipped list[str]; destructive; must pause and ask me before deleting). No interview tool. Resources/prompts: whatever you infer, my answer is no. Implement both use cases with pathlib inside the workspace root (refuse anything outside it), write tests that create junk dirs in tmp_path and drive remove_junk through the client with an elicitation callback that accepts, run all checks and show output, write the repo's .mcp.json and validate it with the MCP config validator that ships with the plugin.
