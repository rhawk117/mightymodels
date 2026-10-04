#!/usr/bin/env bash
set -eu
plugin=fixtures/plugin
mkdir -p "$plugin/.claude-plugin" "$plugin/skills/tf-plan" "$plugin/agents"
cat > "$plugin/.claude-plugin/plugin.json" <<'JSON'
{
  "name": "tf-helpers",
  "version": "0.2.0",
  "description": "Terraform helpers for the platform team",
  "keywords": ["terraform", "iac"],
  "author": { "name": "Platform Team" }
}
JSON
cat > "$plugin/skills/tf-plan/SKILL.md" <<'MD'
---
name: tf-plan
description: Summarise a Terraform plan. Use when the user asks what a plan will change.
---

# Summarise a plan

Fixture sentinel tf-plan: read the plan output and list creates, updates and deletes.
MD
cat > "$plugin/agents/tf-refactor.md" <<'MD'
---
name: tf-refactor
description: Refactor Terraform modules without changing their behaviour. Use when asked to restructure a module.
tools: Read, Grep, Edit
---

Fixture sentinel tf-refactor: restructure the module and keep the plan output identical.
MD
cat > "$plugin/.mcp.json" <<'JSON'
{
  "mcpServers": {
    "tflint": {
      "command": "uv",
      "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/mcp/tflint", "tflint"]
    }
  }
}
JSON
