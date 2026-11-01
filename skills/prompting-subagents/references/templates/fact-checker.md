# Template: fact-checker dispatch

For one finished task inside an active mightymodels sprint, after its implementer (engineer, architect or intern) reported it done. fact-checker checks the brief's DONE half against its ASKED half on the assertion criteria and reads the task's commit for quality. Its standing contract (the 25 tool-call budget, verdicts, the rule for a blocking finding, report format) lives in the fact-checker agent file; carry only what varies per dispatch. Only the main conversation dispatches it: no worker's dispatch row names it.

**Ten-second checklist:** the brief has its `## DONE` half with a `commit:` line · the commit is the one the implementer reported and is HEAD · the criterion ids listed are the assertions only, because the command criteria are not the fact-checker's: the implementer ran them in sandboxed Bash and cited the output in its DONE half · the slug and task id are the ones `task_start` was called with · the model is `haiku`.

```text
<objective>Check task <Tn> of ticket <slug> before it closes: each assertion criterion against the code at the commit, and the commit's diff for quality.</objective>
<context>
Brief: .mightymodels/<slug>/briefs/task-NN.md
Ticket slug: <slug>. Task: <Tn>. Commit: <hash from the implementer's report>.
Assertion criteria: <AC-2, AC-3>. <Command criteria, which are not yours: AC-1.>
</context>
```

Slots: task id · slug · brief path · commit · assertion criterion ids · command criterion ids.

The fact-checker stops at 25 tool calls and marks every criterion it did not reach `UNCHECKED`, so list only the criteria worth checking.

## When it comes back

- `CLEAR`: each criterion's `location` is the citation `task_verify` takes under `assertions`.
- `HOLD` on a `REFUTED` criterion, or on a finding with `blocking="true"` (Critical or High, citing a file and line and the criterion or rule it breaks): the task stays open and routes as a failed verification does, with the finding verbatim in the next ASKED.
- `HOLD` on an `UNCHECKED` criterion only: send the same fact-checker the narrower question through `SendMessage`; a criterion still unchecked after that is one you open and cite yourself.
- A finding with `blocking="false"` never holds the task. Record it in the brief under `## FINDINGS`: a Medium or Low one as it stands, and one that lacks the line or the rule as `advisory` whatever its severity. review-circus picks the recorded findings up.
