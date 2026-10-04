---
description: Plugin-scope MCP server for Terraform inspection, built through the create-mcp interview answers given upfront.
expected_outcome: A uv project under mcp/tf-inspect in the plugin with both tools, checks run, a plugin .mcp.json in the Claude Code shape, and a validator pass.
tags: [create-mcp]
runs: 1
max_turns: 80
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Bash, Write, Edit]
---

Add an MCP server to my plugin at fixtures/plugin so Claude Code can inspect Terraform modules without me pasting plan output into chat. Two tools: one that summarises a `terraform show -json` plan file (counts of create/update/delete/replace and the list of replaced addresses), and one that runs `terraform validate` in a module directory and returns whether it passed and the diagnostics.

Everything you'd otherwise ask me: plugin scope; the server name is tf-inspect. Local only. The server finds the project root through the environment variable Claude Code sets for it. Problem: reviewers miss replacements buried in long plans and Claude keeps running terraform in the wrong directory. Tool 1 plan_summary: input plan_path (str, path to the JSON plan relative to the repo root), outputs create_count/update_count/delete_count/replace_count (int) and replaced_addresses (list[str]); read-only. Tool 2 validate_module: input module_dir (str, relative); outputs passed (bool) and diagnostics (list[str]); read-only; runs the terraform binary. No tool needs to pause and ask me. No interview tools. If you think a resource or prompt fits, propose it and take my answer as no. Implement both use cases (for plan_summary parse the JSON; for validate_module run `terraform validate -json` through the workspace; terraform is not installed here, so make the test for it assert the failure is reported as a ToolError rather than a crash, and use a hand-written plan JSON fixture for plan_summary). Run every check and show me the output. Write the plugin's .mcp.json and validate it with the MCP config validator that ships with the plugin.
