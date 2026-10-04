---
description: Extending an existing plugin that already ships a tflint MCP server with an agent and a rule, planned but not built.
expected_outcome: The inventory runs first and shows the built components, the plan adds the tflint-runner agent and routes the rule to outside_plugin, and render with force rewrites only the plan files and manifest.
tags: [plan-plugin]
runs: 1
max_turns: 60
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Bash, Write, Edit]
---

I want to add an agent to my plugin at fixtures/plugin that runs tflint on a module and returns only the findings, and a rule that our modules always pin provider versions. Plan it, don't build it.

Everything you'd otherwise ask me: extension of the existing plugin. Problem: reviewers repeat the same provider-pin comment and nobody runs tflint before asking for review. Audience: my team (team). Kind: ecosystem, Terraform. Keep the existing name and keywords. Agent: name tflint-runner, tools Bash (tflint only) and Read, cheap model is fine, returns findings as file:line:rule:message, the main agent delegates when asked to lint or before a review. Rule: name provider-pinning, applies to **/*.tf, steering only. If you think the agent is the wrong mechanism because the plugin already ships a tflint server, tell me why and my answer is: keep the agent. Distribution: local directory for now. Write the record and the plan.
