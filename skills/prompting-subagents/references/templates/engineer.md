# Template: engineer dispatch (emits the ASKED stanza)

For one task dispatch inside an active mightymodels sprint. This template's first output block IS the brief's `## ASKED` half — write it once, paste it to the top of `.mightymodels/<slug>/briefs/task-NN.md`, and include it in the dispatch. The engineer's standing contract (report format, scope rules, blast-radius doctrine) lives in the engineer agent file — do not restate it.

**Ten-second checklist:** every acceptance line is an outcome sentence a reader can observe, with no id and no command; "works correctly" is a placeholder, reject it · verification names the tests or checks the worker runs, scoped, and they exist in this repo (check the runner config before promising them) · files-in-scope is disjoint from any other open group's set · interface lists the signatures the change adds or alters, or says None · reuse-or-delete names the code to reuse and the code to delete, or says None · tier bump, if any, has its reason logged · uses names the repository skills or instruction files the task needs, when it needs any · the toolchain lines are pasted from `toolchain.md` (a hook the commit runs, a lint ban, a sandbox denial, a tool the task can use), never recalled, and they tell the worker to run scoped checks and to report a sandbox wall instead of changing code to get past it.

ASKED stanza (goes in the brief AND the dispatch):

```text
## ASKED
objective: <one sentence — what and why>
acceptance:
  - <outcome sentence: what is true when the task is done, in terms a reader can observe>
  - <...>
verification: <the tests or checks to run, scoped, in order; the worker runs them in sandboxed Bash and names each in its report with the output quoted>
files-in-scope: [<paths this task owns>]
interface: <signatures the change adds or alters, or None>
reuse-or-delete: <code to reuse and code to delete, or None>
engineer-tier: <model from ticket.yml, or bumped one tier: reason>
uses: [<repository skills or instruction files, when the task names them>]
toolchain: [<the TC lines of .mightymodels/<slug>/toolchain.md that bind this task, verbatim; left out on a ticket with no survey>]
```

Dispatch wrapper around the stanza:

```text
<objective>Execute the task specified in the ASKED stanza below. Brief path: .mightymodels/<slug>/briefs/task-NN.md — append your ## DONE section there before reporting (≤65 lines, with `commit: <hash>` on a line of its own, which the fact-checker and the primary read, and each test run by name with its output quoted).</objective>

<ASKED stanza here>

<constraints>Commit when done with message "<message>" and never push.
</constraints>
```

Slots: objective · acceptance sentences · verification · files-in-scope · interface · reuse-or-delete · tier(+reason) · uses · toolchain lines · brief path · commit message.

## Residual variant

For one named residual with a bounded fix: a verification leftover, a mechanical CI failure, or a review finding carrying Fix: and Verify: lines. The finding's own lines are the payload; paste them verbatim, never paraphrase, because paraphrase is where scope creep starts. No brief is written for a residual, so the dispatch itself carries the ticket slug and the task id the brief path would have given. The task id is the one `task_start` just took: `R<n>` for a verification leftover or a review finding, `C<n>` for a CI failure. The finding's own id (`MV-3`, `UB-2`, `FC-1`) is one of the slots below, next to the task id.

**Ten-second checklist:** exactly one issue named · the task id is started · Fix: is a bounded action, not a goal · Outcome is one sentence the Fix makes true · Verify: names the commands the engineer runs · files-in-scope names every file the Fix touches · commit/push instructions explicit.

```text
<objective>Close one residual: <finding id and one-line name>. Treat it as a group of one task with the id <task id>.</objective>
<context><where it came from: which task's verification, which CI check, or which review finding, one line></context>
slug: <ticket slug>
task-id: <the started R<n> or C<n>>
finding: <the finding's own id, or the CI check's name>
files-in-scope: [<every file the Fix touches>]
Fix: <verbatim from the finding or verification failure>
Outcome: <one sentence that is true once the Fix lands>
Verify: <verbatim commands the engineer runs>
<constraints>Commit as "<message>" and never push. One attempt: run Verify in sandboxed Bash, scoped, and name each test run with its output quoted; the residual needs only a commit inside files-in-scope. Report a sandbox wall instead of changing code to get past it. If Verify still fails, report failed with the output tail; if the Fix needs a file outside files-in-scope, report blocked.</constraints>
```

Slots: finding id · source line · slug · task id · files-in-scope · Fix · Outcome · Verify · commit message.
