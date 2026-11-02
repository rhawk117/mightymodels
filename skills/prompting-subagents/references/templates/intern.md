# Template: intern dispatch

For one `tiny` task inside an active mightymodels sprint, given to the intern for a single attempt. A task is `tiny` when it owns exactly one file and the change is mechanical; any other task goes to the engineer. The brief's `## ASKED` half is the one the engineer template emits (`engineer.md`), `interface` and `reuse-or-delete` slots included; write it once, paste it to the top of `.mightymodels/<slug>/briefs/task-NN.md`, and include it in the dispatch. The intern's standing contract (one attempt, report format, scope rules) lives in the intern agent file; do not restate it.

**Ten-second checklist:** every acceptance line is an outcome sentence the named tests or checks settle on their own, because the intern does not interpret · the verification names scoped tests or checks that exist in this repo · interface and reuse-or-delete are filled, or say None · files-in-scope names the one file the task owns · the task was started with `by` `intern` and that one file as its owned set, because the dispatch hook refuses the intern on any other started task · the commit message is in the packet.

```text
<objective>Execute the task specified in the ASKED stanza below, in one attempt. Brief path: .mightymodels/<slug>/briefs/task-NN.md. Append your ## DONE section there before reporting (30 lines at most, with `commit: <hash>` on a line of its own, which the fact-checker and the primary read, and each test run by name with its output quoted).</objective>

<ASKED stanza here>

<constraints>Run each verification command in sandboxed Bash, scoped as written, and cite its output as evidence. Report a sandbox wall instead of changing code to get past it. Commit when done with message "<message>" and never push.
</constraints>
```

Slots: objective · acceptance sentences · verification · files-in-scope · interface · reuse-or-delete · uses · toolchain lines · brief path · commit message.

## When it comes back blocked

The intern does not debug and is not dispatched again on the same task; `task_start` refuses a second attempt by it. Mark the task `blocked` (`task_mark`) with the intern's blocker as the reason, start it with `by` `engineer` and the same owned set and acceptance, and dispatch the engineer with the same ASKED stanza and the intern's blocker in `<context>`. No question goes to the user for this handover.
