---
type: llm
focus: last_message
---

PASS if the final reply tells the person to run the hook session first, then the skill, then the agent, then the install-and-verify session (4.1), and lists what is unverified.

FAIL if the order differs, or if it builds any component itself.
