# The .mightymodels/ directory

Per-ticket, sparse, organized by unit of work. The unit of deletion is the unit of work: `/prune-ticket` removes a whole ticket directory, so rot cannot outlive its ticket.

```
.mightymodels/
├── <task-slug>/
│   ├── ticket.yml                     source of truth (see ticket-schema.md)
│   ├── work-unit.json                 staged state: ticket section from validate, progress from the loop
│   ├── plan.md                        game-plan ramp only; high-level, citation-free
│   ├── transitions.jsonl              task_state.py's append-only transition log
│   ├── verification/contract.json     user-approved commands (verification.py)
│   ├── verification/receipts.jsonl    one receipt per run, stamped with HEAD
│   ├── issue-body.md                  when no forge issue was created, or as the local draft
│   ├── pr-body.md                     stick-the-landing's checked PR body
│   ├── handoffs/snapshot.{json,md}    baton-pass's snapshot.py: objective state from the files above
│   ├── handoffs/BATON.md              mid-work handoff, ≤40 lines, facts that live nowhere else
│   ├── briefs/task-NN.md              two halves, ≤80 lines (contracts.md)
│   ├── review/<run>/                  one review-circus run (review_state.py): review-run.json,
│   │                                  findings.jsonl, persona reports, metrics, report.md
│   ├── whats-broken.md                only while a debug is live; regenerated per attempt
│   └── REPORT.md                      ≤50 lines, sprint summary
├── .runtime/investigations/<id>.jsonl  lets-investigate ledgers (ledger.py is the only writer)
├── .runtime/reviews/<run>/          review runs with no ticket (review_state.py)
├── .runtime/subagents/receipts.jsonl  worker stop receipts (subagent-recorder hook), ticket-tagged
├── .runtime/decisions/receipts.jsonl  ask_user answers (decision-recorder hook), ticket-tagged
├── .runtime/gate/<sha256>            completion-gate's one-block-per-worker markers
└── archives/<task-slug>.{md,json}     ≤30-line archive plus bounded JSON record, written by prune-ticket's archive_ticket.py
```

## Writer/reader matrix — one writer per file class

| Path                                       | Writer                                                                                          | Readers                                                  |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| ticket.yml                                 | open-ticket's ticket_state.py, or one-shot when ramping without a ticket (then the user's hand) | every session                                            |
| plan.md                                    | game-plan primary, after user approval                                                          | primary, dispatch compilation                            |
| briefs/ ASKED half                         | primary at dispatch                                                                             | engineer, verifying scout                                |
| briefs/ DONE half                          | engineer                                                                                        | primary, verifying scout                                 |
| review/<run>/                              | review-circus: review_state.py for run state, the primary for persona reports and metrics       | review-circus, stick-the-landing, prune-ticket, the user |
| work-unit.json progress, transitions.jsonl | agents-assemble's task_state.py                                                                 | agents-assemble, stick-the-landing, baton-pass           |
| verification/                              | game-plan's verification.py                                                                     | task_state.py, every skill that proves work              |
| pr-body.md                                 | stick-the-landing                                                                               | `gh pr create`                                           |
| handoffs/                                  | baton-pass                                                                                      | the next session's primary                               |
| REPORT.md                                  | agents-assemble primary                                                                         | stick-the-landing, review-circus, prune-ticket           |
| archives/                                  | prune-ticket's archive_ticket.py                                                                | future humans and sessions                               |

## Thinness rule for handoffs

`BATON.md` carries only facts that live nowhere else. It is a bootstrap pointer — read ticket.yml, read issue #N, your role, what to invoke — plus nothing. Duplicated facts drift, and the next session reads ticket.yml first anyway.

## Never tracked

Nothing under `.mightymodels/` is ever committed. `open-ticket`'s `ticket_state.py` (on every `write` and `validate`), `ledger.py` (on `start` and `add`), and `review_state.py` (on `start`) add `.mightymodels/` to the repository's local exclude file (`info/exclude` in the common git dir, so worktrees share it). `briefs/`, `review/`, and the ledgers carry raw command output that can hold secrets, and local-only exclusion means a careless `git add -A` cannot ship them. A later session that finds `.mightymodels/` missing from the exclude file restores it before writing anything there.
