# mightymodels contracts

The shared vocabulary of the mightymodels loop. Every mightymodels skill and agent cites this file instead of defining its own; one severity means one thing everywhere, and a report one skill writes is a report the next skill can parse. When two artifacts disagree with this file, this file wins and the artifact gets fixed.

## Severity table

| Severity | Anchor                                                                                                                                                                                                                                                |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Critical | Merging or shipping causes harm now: exploitable defect reachable from an untrusted boundary, committed secret (including branch history), removed authn/authz enforcement, data-loss path                                                            |
| High     | Unacceptable risk, or removes the net that catches future defects: deleted/skipped test without replacement, weakened CI gate, breaking change with confirmed live callers, silently dropped plan commitment, security defect requiring preconditions |
| Medium   | Costs real time later: new logic without tests, public doc drift, swallowed errors, compounding maintainability debt, unjustified non-security suppressions                                                                                           |
| Low      | Nits, style, internal doc drift                                                                                                                                                                                                                       |

Cross-reviewer mapping: uncle-bob's `Blocker` maps to **High**; its High/Medium/Low map straight across. When two reviewers flag the same defect at different severities, the higher wins and both are noted; a gap of two or more levels is flagged for the user's judgment.

## Verdict vocabularies (per role, consumed by the coordinator)

| Role                 | Vocabulary                                                                          | Meaning of the hard state                                                                                                                                                                                                                                                 |
| -------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| code-scout           | `VERIFIED` / `INFERRED` / `NEEDS-ANALYSIS` / `UNKNOWN-BLOCKED`                      | UNKNOWN-BLOCKED: the answer is not in what it can read, and it names where the answer lives                                                                                                                                                                               |
| web-scout            | `VERIFIED` / `INFERRED` / `NEEDS-ANALYSIS` / `UNKNOWN-BLOCKED`                      | UNKNOWN-BLOCKED: the answer is not in what it can fetch, and it names where the answer lives                                                                                                                                                                              |
| fact-checker         | `CLEAR` / `HOLD` / `UNKNOWN-BLOCKED`; per criterion `VERIFIED`, `REFUTED`, or `UNCHECKED` | HOLD: a criterion is refuted or unchecked, or a finding is blocking, and it advises the primary to keep the task open. A finding blocks only when it is Critical or High and cites a file and line and the criterion or rule it breaks; one without both is recorded as advisory, and a Medium or Low one is recorded in the brief for review-circus |
| engineer             | `done` / `failed` / `blocked` / `too-large`; per task `verified` = `true`, `false`, or `deferred` | failed: edits made but a required verification still fails after its failed fixes (up to three, each recorded with `failed_fix`); blocked: dispatch incomplete or plan wrong on the ground. Both route to the architect, after the owner is asked unless `auto-escalate` is on. too-large: more than one reviewable unit of work; the report names where to cut, nothing is committed, and it routes to break-it-down |
| architect            | `completed` / `replanned` / `scope-expansion-requested` / `too-large` / `blocked`   | scope-expansion-requested: the durable fix needs files outside the envelope; the coordinator or user approves before a systemic-refactor dispatch. replanned: one task with a revised ASKED. too-large: several tasks; the result names where to cut and routes to break-it-down                                |
| task (the task tools) | `pending` / `in-progress` / `verified` / `failed` / `blocked` / `superseded` | verified, failed, blocked: the primary's verdict, recorded with `task_verify` (commit, verdict, and a reason unless verified); the tool returns the facts `commit_is_head`, `base_status` and `outside_owned` and does not change the verdict on them. superseded: a replanned task, closed so `ready` can pass. `Tn` are plan tasks (plain numbers, never dotted), `Cn` CI fixes during stick-the-landing, `Rn` residuals, each the next free `R<n>` whoever starts it: a verification leftover from the loop or a review-circus finding, whose own id is never the task id |
| gitty-up (ci)        | `pass` / `fail` / `error`                                                           | error: checks absent, pending, or unresolvable — never treated as pass                                                                                                                                                                                                    |
| review               | `BLOCK` / `MERGE WITH CONDITIONS` / `CLEAR`                                         | CLEAR is impossible while any security-relevant question sits UNKNOWN-BLOCKED                                                                                                                                                                                             |

## The two-half task brief

`briefs/task-NN.md`, 80 lines total, roughly 15 ASKED, up to 65 DONE. The ASKED half is written by the primary at dispatch (prompting-subagents' engineer template emits it); the DONE half is appended by the implementer on completion. The fact-checker checks DONE against ASKED criterion by criterion, reruns the verification, and reads the task's commit for quality; the primary compares its report with the implementer's. Its findings that do not hold the task are recorded by the primary under `## FINDINGS`, after the DONE half and inside the same 80 lines, one line each: `FC-n | severity | file:line | criterion or rule | evidence`, with `advisory` in front of one that lacks the line or the criterion or rule.

```markdown
## ASKED
objective: <one sentence>
acceptance:
  - <an outcome sentence a worker can check at a named place, with no id and no command>
verification: <commands, in order>
files-in-scope: [<paths this task owns>]
interface: <signatures, shapes or names other tasks rely on>
reuse-or-delete: <what to reuse, what to delete>
engineer-tier: <model from ticket.yml, or bumped one tier: reason>
toolchain: [<the TC lines of toolchain.md that bind this task, verbatim; left out with no survey>]

## DONE
what: <what changed>
commit: <hash>
diff-summary: <one paragraph>
tests: <test names>
commands-run: <verification commands + quoted output>
```

"Works correctly" is not an acceptance criterion: every criterion is an outcome someone can check at a named location, and the `verification:` line carries the commands that prove it. A placeholder criterion makes the verification step theater.

## Finding format (reviews and remediation)

`<ID> | <severity> | <file:line> | evidence (at most one quoted line) | why it matters (1-2 sentences) | Fix: <action an engineer takes without re-deriving the analysis> | Verify: <command or grep that confirms the fix> | Confidence: <High|Low>`

IDs are stable within their report (MV-n, UB-n) and aggregation preserves provenance.

## Caps are contracts

Brief 80 lines · REPORT.md 50 · archive 30 · plan.md ~200 · one task is meant to stay near three owned files and four acceptance criteria: `task_start` starts a larger one anyway and its warning names break-it-down · whats-broken.md current-state only, regenerated per attempt · one architect implementation attempt per task, plus one `systemic-refactor` pass after an approved scope expansion; `diagnose-replan` passes never count against it. Hitting a cap means the content belongs in a different layer, not that the file grows.

## Durable-before-advance

Workflow state advances only after the evidence for it is externalized; recovery reads
artifacts, never conversation. The per-task order is fixed: `task_start` records the attempt and its owned set; the
engineer commits, appends the DONE half (with the commit hash) to the brief, then reports; the
fact-checker checks the criteria, reruns the verification and reads the commit's diff; the
primary compares the two reports and records its verdict with `task_verify`; only then does the loop
advance. On recovery, a commit with no DONE half is an incomplete task and an unrecorded
verdict is an unverified task, and worker conversational state is never authoritative.

The primary is a skeptical manager: workers do the work and the checking, and it looks further
only on a contradiction or on vagueness, so its own context stays free for the decisions.

Nothing is pushed until `task_ready` answers `ready` (every plan task verified or superseded, no
`Cn` or `Rn` task failed or blocked) and CI passes; CI is the hard gate, and no other hold applies.

## Rot rules

Regenerate, never append — history lives in git, the issue, and the PR. Paths, not pastes — agents receive `.mightymodels/` file paths in dispatches; wholesale pasting is how one stale paragraph outlives three recompiles. Citations expire — a file carrying file:line citations records the commit they were read at; consumers whose HEAD has moved treat it as expired.
