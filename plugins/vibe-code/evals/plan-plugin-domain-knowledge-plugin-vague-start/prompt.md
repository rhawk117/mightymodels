---
description: New release-process plugin from a vague start, with a human-only skill, an agent and a Stop hook, all kept as planned.
expected_outcome: The problem is recorded verbatim, the skill is human-only, the agent is limited to git and uv, the Stop hook checks stop_hook_active, and the phases put the hook first, then the skill and agent, then verify.
tags: [plan-plugin]
runs: 1
max_turns: 60
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Bash, Write, Edit]
---

We want a plugin so Claude Code knows how we do releases. Target dir fixtures/new/release-kit.

Everything you'd otherwise ask me: new plugin. When you ask what goes wrong today: release branches get cut without the changelog, the version bump is forgotten in pyproject, and people run the release workflow with the wrong tag. Audience: the whole engineering org (org), read-only users who just install it. Kind: domain knowledge plus workflow. Name release-kit, keywords release, changelog, versioning, tags, workflow; description 'Our release process, as skills Claude Code can follow'. Components: a human-only skill /cut-release that walks the steps; an agent named release-verifier that verifies a release candidate (checks changelog entry, version, tag) with Read and Bash limited to git and uv; a hook that blocks Claude from finishing a release task if the changelog is missing. No MCP, no rules, no commands. Distribution: a marketplace in our git repository. If any component is the wrong mechanism, say why; my answer is don't care, keep it as planned. Write the record and shell.
