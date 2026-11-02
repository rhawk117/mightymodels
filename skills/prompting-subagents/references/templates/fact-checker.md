# Template: fact-checker dispatch

For one finished task inside an active mightymodels sprint, after its implementer (engineer, architect or intern) reported it done. fact-checker reads the task's commit, reruns the tests the implementer named, rules on each outcome sentence of the brief with a file:line, and reads the diff for quality. It advises; the primary decides. Its standing contract (the 25 tool-call budget, verdicts, the rule for a blocking finding, report format) lives in the fact-checker agent file; carry only what varies per dispatch. Only the main conversation dispatches it: no worker's dispatch row names it.

**Ten-second checklist:** the brief has its `## DONE` half with a `commit:` line and the tests the implementer ran by name · the commit is the one the implementer reported · the base is the commit the task started from · the slug and task id are the ones `task_start` was called with · the model is `haiku`.

```text
<objective>Check task <Tn> of ticket <slug> before it closes: each outcome sentence of the brief against the code at the commit, the named tests rerun, and the commit's diff for quality.</objective>
<context>
Brief: .mightymodels/<slug>/briefs/task-NN.md
Ticket slug: <slug>. Task: <Tn>. Commit: <hash from the implementer's report>. Base: <hash>.
</context>
```

Slots: task id · slug · brief path · commit · base. The outcome sentences are read from the brief, not pasted into the packet.

The fact-checker stops at 25 tool calls and marks every sentence it did not reach `UNCHECKED`.

## When it comes back

Each outcome sentence is `VERIFIED` or `REFUTED` with a file:line, or `UNCHECKED` with the reason; the overall `CLEAR`, `HOLD` or `UNKNOWN-BLOCKED` is advice, and you compare it with the implementer's DONE half before you record your own verdict with `task_verify`.

- `CLEAR`: advice that the task can close. A rerun that differs from the output the implementer quoted is a contradiction to settle first.
- `HOLD` on a `REFUTED` sentence, or on a finding with `blocking="true"` (Critical or High, citing a file and line and the sentence or rule it breaks): advice to keep the task open and route it as a failed verification, with the finding verbatim in the next ASKED.
- `HOLD` on an `UNCHECKED` sentence only: send the same fact-checker the narrower question through `SendMessage`; a sentence still unchecked after that is one you open and cite yourself. A test the sandbox stopped it running comes back with its output: hand the user the exact `!` command, never run it with the sandbox off.
- A finding with `blocking="false"` never holds the task. Record it in the brief under `## FINDINGS`: a Medium or Low one as it stands, and one that lacks the line or the rule as `advisory` whatever its severity. review-circus picks the recorded findings up.
