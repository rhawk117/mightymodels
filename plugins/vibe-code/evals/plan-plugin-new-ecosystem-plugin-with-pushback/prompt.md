---
description: New Terraform plugin where two components are the wrong mechanism and the person accepts the proposed switches upfront.
expected_outcome: A validated plugin-plan.json and shell for tf-guard; the apply and destroy denial lands in outside_plugin as a permissions entry, validate_module becomes a skill with allowed-tools, the fmt hook and the plan-review skill stay, and PLAN.md has four ordered phases with ready prompts.
tags: [plan-plugin]
runs: 1
max_turns: 60
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Bash, Write, Edit]
---

I want a Claude Code plugin for our Terraform repos. It should stop Claude from running terraform apply or destroy, always run terraform fmt after edits, review plans for replacements, and give Claude a way to validate a module. Put it at fixtures/new/tf-guard.

Everything you'd otherwise ask me: new plugin. Problem: Claude sessions in our IaC repos have applied plans nobody reviewed, leave files unformatted, and miss replace-in-place resources buried in long plans. Audience: the SRE team (team), installed via our internal marketplace `sre-tools`. Kind: ecosystem harness, Terraform. Name tf-guard, keywords terraform, iac, sre, plan-review, fmt; description 'Guardrails and helpers for Terraform work in Claude Code sessions'. Components as I described them: a hook that denies apply/destroy, a hook that runs fmt after edits, a skill that reviews a plan for replacements (model may auto-load it), and an MCP server with a validate_module tool (local only, read-only, runs the terraform binary, acts on the repo). If you think any of those is the wrong mechanism, tell me why and take my answer as: switch to what you propose. No rules, no commands. Distribution marketplace. Write the record and the shell and show me the ready prompts.
