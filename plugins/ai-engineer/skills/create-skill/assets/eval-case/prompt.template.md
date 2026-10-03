---
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
# Optional; keep only what the case needs.
# name: CASE_NAME
# description: FOR_HUMANS
# tags: [smoke]
# runs: 3
# model: MODEL_ID
# timeout_seconds: 300
# append_system_prompt: TEXT_APPENDED_TO_THE_SYSTEM_PROMPT
# env: { EVAL_NAME: VALUE }
---

WHAT_THE_USER_TYPES, phrased the way a user would type it, without naming the skill.

Everything you'd otherwise ask me: ANSWERS_TO_EVERY_QUESTION_THE_SKILL_ASKS.
