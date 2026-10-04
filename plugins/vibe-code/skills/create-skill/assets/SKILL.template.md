---
name: NAME
description: WHAT_IT_DOES_AND_WHEN_TO_USE_IT, key use case first
when_to_use: TRIGGER_PHRASES_AND_EXAMPLE_REQUESTS
argument-hint: "[ARGUMENT_HINT]"
disable-model-invocation: false
user-invocable: true
# Optional lines; keep only the ones the user chose in phase B, delete the rest.
# arguments: [FIRST_ARGUMENT]
# paths: ["GLOB"]
# context: fork
# agent: AGENT_TYPE
# hooks: see the create-hooks skill for the format
---

# TITLE

ONE_PARAGRAPH: what this skill does, the problem it solves, and why the steps below are shaped the way they are. Written for the model that will follow it, so it can generalise beyond the exact cases it was tested on. Put the instructions that matter most near the top: only the first 5,000 tokens survive compaction.

## When it applies

- SITUATION_1
- SITUATION_2
- Not for NEGATIVE_SITUATION; that is handled by ALTERNATIVE.

## Context

Delete this section unless the skill always needs live data.

- STATE_LABEL: !`COMMAND_THAT_PRINTS_THE_STATE`

## Before starting

- Read `references/REFERENCE.md` when CONDITION.
- Confirm PRECONDITION (for example: the working tree is clean, the runner is installed); if it does not hold, say so and stop rather than working around it.

## Procedure

1. STEP_1. WHY_IT_MATTERS.
2. STEP_2. Run `python3 ${CLAUDE_SKILL_DIR}/scripts/SCRIPT.py ARGS` and show its output; do not re-derive what the script checks.
3. STEP_3. If CHECK fails, DO_THIS instead of continuing, because CONSEQUENCE.

## Output

Describe the exact shape of what the user receives (file paths, a summary, a table), so runs are comparable.

## Hand off

State what was done, what was not verified, and the one command the user can run to check the result themselves.
