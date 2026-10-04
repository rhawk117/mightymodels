---
description: Command-wrapping MCP request where a skill is the better mechanism and the person overrides the advice upfront.
expected_outcome: The routing advice is given and recorded, the override is honoured, and check-runner is built in the repo with both use cases through the workspace runner.
tags: [create-mcp]
runs: 1
max_turns: 80
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Bash, Write, Edit]
---

Make me an MCP server that runs ruff check and pytest for Claude Code so it stops forgetting to run them. Repo is fixtures/repo, put it in the repo.

Everything you'd otherwise ask me: project scope, server name check-runner, local only. The server finds the project root through the environment variable Claude Code sets for it. If you tell me something else fits better, my answer is: don't care, build the MCP anyway. Tools: run_ruff (no inputs beyond the root handling you need; outputs passed bool and findings list[str]; read-only; binary ruff via uv) and run_pytest (input: target str default tests; outputs passed bool and summary str; read-only; binary uv). No pauses, no interview tools, no resources or prompts. Implement both use cases through the workspace tool runner (uv is installed here, so the tests can run the real commands against the fixture repo copied into tmp_path), run all checks, show output, write the config and validate it.
