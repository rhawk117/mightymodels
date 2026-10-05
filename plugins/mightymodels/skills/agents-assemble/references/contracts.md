# mightymodels contracts

The shared vocabulary of the mightymodels loop. Every mightymodels skill and agent cites this file instead of defining its own; one severity means one thing everywhere, and a report one skill writes is a report the next skill can parse. When two artifacts disagree with this file, this file wins and the artifact gets fixed.

## Severity table

| Severity | Anchor                                                                                                                                                                                                                                                |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Critical | Merging or shipping causes harm now: exploitable defect reachable from an untrusted boundary, committed secret (including branch history), removed authn/authz enforcement, data-loss path                                                            |
| High     | Unacceptable risk, or removes the net that catches future defects: deleted/skipped test without replacement, weakened CI gate, breaking change with confirmed live callers, silently dropped plan commitment, security defect requiring preconditions |
| Medium   | Costs real time later: new logic without tests, public doc drift, swallowed errors, compounding maintainability debt, unjustified non-security suppressions                                                                                           |
| Low      | Nits, style, internal doc drift                                                                                                                                                                                                                       |

Cross-reviewer mapping: uncle-bob's `Blocker` maps to **Critical**; its High/Medium/Low map straight across. When two reviewers flag the same defect at different severities, the higher wins and both are noted; a gap of two or more levels is flagged for the user's judgment.

## Verdict vocabularies (per role, consumed by the coordinator)

| Role                 | Vocabulary                                                                          | Meaning of the hard state                                                                                                                                                                                                                                                 |
| -------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| code-scout           | `VERIFIED` / `INFERRED` / `NEEDS-ANALYSIS` / `UNKNOWN-BLOCKED`                      | UNKNOWN-BLOCKED: the answer is not in what it can read, and it names where the answer lives                                                                                                                                                                               |
| web-scout            | `VERIFIED` / `INFERRED` / `NEEDS-ANALYSIS` / `UNKNOWN-BLOCKED`                      | UNKNOWN-BLOCKED: the answer is not in what it can fetch, and it names where the answer lives                                                                                                                                                                              |
| engineer             | `done` / `failed` / `blocked`; per task `verified` = `true`, `false`, or `deferred` | failed: edits made but a required verification still fails after its one attempt; blocked: dispatch incomplete or plan wrong on the ground. Both route to architect                                                                                                       |
| architect            | `completed` / `replanned` / `scope-expansion-requested` / `blocked`                 | scope-expansion-requested: the durable fix needs files outside the envelope; the coordinator or user approves before a systemic-refactor dispatch                                                                                                                         |
| task (task_state.py) | `pending` / `in-progress` / `verified` / `failed` / `blocked`                       | verified: every `Tn.*` (or `Cn.*`) contract command passed at HEAD, every other AC cited, commit inside the owned set; checked by the script, never asserted. `Tn` are plan tasks, `Cn` CI fixes during stick-the-landing, `Rn` review-circus remediation of finding `Fn` |
| gitty-up (ci)        | `pass` / `fail` / `error`                                                           | error: checks absent, pending, or unresolvable — never treated as pass                                                                                                                                                                                                    |
| review               | `BLOCK` / `MERGE WITH CONDITIONS` / `CLEAR`                                         | CLEAR is impossible while any security-relevant question sits UNKNOWN-BLOCKED                                                                                                                                                                                             |

## The two-half task brief

`briefs/task-NN.md`, 80 lines total — roughly 15 ASKED, up to 65 DONE. The ASKED half is written by the primary at dispatch (prompting-subagents' engineer template emits it); the DONE half is appended by the engineer on completion. The scout verification step checks DONE against ASKED, criterion by criterion.

```markdown
## ASKED
objective: <one sentence>
acceptance:
  - AC-1: <runnable command, or checkable assertion naming a file/behavior>
verification: <commands, in order>
files-in-scope: [<paths this task owns>]
engineer-tier: <model from ticket.yml, or bumped one tier: reason>
uses: [<repo skills/instruction files, when named>]

## DONE
what: <what was done>
commit: <hash>
diff-summary: <one paragraph>
commands-run: <verification commands + observed results>
```

"Works correctly" is not an acceptance criterion — every AC is a command someone can run or an assertion someone can check at a named location. A brief with a placeholder AC is refused at write time, because an uncheckable criterion makes the verification step theater.

## Finding format (reviews and remediation)

`<ID> | <severity> | <file:line> | evidence (at most one quoted line) | why it matters (1-2 sentences) | Fix: <action an engineer takes without re-deriving the analysis> | Verify: <command or grep that confirms the fix> | Confidence: <High|Low>`

IDs are stable within their report (MV-n, UB-n) and aggregation preserves provenance.

## Caps are contracts

Brief 80 lines · REPORT.md 50 · archive 30 · plan.md ~200 · whats-broken.md current-state only, regenerated per attempt · one architect recovery per task, plus one pass after an approved scope expansion. Hitting a cap means the content belongs in a different layer, not that the file grows.

## Durable-before-advance

Workflow state advances only after the evidence for it is externalized; recovery reads
artifacts, never conversation. The per-task order is fixed: `task_state.py start` records the attempt and its owned set; the
engineer commits, appends the DONE half (with the commit hash) to the brief, then reports; the
contract commands run through `verification.py` and code-scout checks the assertion ACs;
`task_state.py verify` records the outcome in `work-unit.json` and `transitions.jsonl`; only
then is the task's box checked. On recovery, a commit with no DONE half is an incomplete task and an unrecorded
verification is an unverified task — worker conversational state is never authoritative.

Nothing is pushed until `task_state.py ready` exits 0: every plan task verified, no task
failed or blocked, and every contract command passing at the current HEAD. A commit after
the last verification makes every receipt stale, so a push after a CI fix follows
`verification.py run --all --phase landing`.

## Rot rules

Regenerate, never append — history lives in git, the issue, and the PR. Paths, not pastes — agents receive `.mightymodels/` file paths in dispatches; wholesale pasting is how one stale paragraph outlives three recompiles. Citations expire — a file carrying file:line citations records the commit they were read at; consumers whose HEAD has moved treat it as expired.
