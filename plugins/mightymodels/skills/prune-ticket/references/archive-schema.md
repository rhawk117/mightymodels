# Archive schema (version 1)

Read before closing a ticket and before changing `scripts/archive_ticket.py`, its only writer.

## Files

`.mightymodels/archives/SLUG.md` (30 lines at most) and `SLUG.json`, never tracked by git. A slug that was archived before gets `SLUG-2`, `SLUG-3`; `work-unit.json` records which one in its `archive` field when the unit closes.

## Live work (`check`, and `close` before it writes)

- a task in work-unit progress that is not `verified` (plan `T`, CI `C`, and review `R` tasks alike);
- a plan task with contract commands that was never started;
- `whats-broken.md` in the ticket directory;
- in the latest review run: a finding with no decision, or one chosen for fixing with no `fixed` outcome;
- the ticket's branch, while it still exists locally, with commits on no remote, or checked out with uncommitted changes to tracked files.

REPORT.md open threads and unchecked tracker tasks are not in any file the script can trust; the skill checks those.

## The JSON record

| Key                                    | From                                                                                               |
| -------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `shipped`, `pr`, `gotchas`             | the closing input (redacted, one line each, at most 3 gotchas)                                     |
| `summary`, `tracker`, `investigations` | `work-unit.json`                                                                                   |
| `tasks`                                | each task's final status and attempts per worker                                                   |
| `verification`                         | every contract command with argv, `expect_exit`, and its latest outcome, HEAD, and digest          |
| `decisions`                            | the last 4 live `decision` entries of the linked ledgers                                           |
| `review`                               | the latest run: id, depth, finding count, ids grouped by outcome or decision, the recorded reasons |
| `agents`                               | this ticket's worker receipts: total, counts by agent and status, the last 10                      |
| `answers`                              | this ticket's recorded ask_user answers: total and the last 10                                     |
| `head`, `closed_at`                    | the repository and clock at close                                                                  |

## Pruning

`prune` without `--confirm` lists what it would remove. With `--confirm`, and only when the unit is closed and both archive files read back, it removes: the ticket directory; each linked ledger that no other ticket's `work-unit.json` links; and this ticket's lines in `.runtime/subagents/receipts.jsonl` and `.runtime/decisions/receipts.jsonl` (lines it cannot parse are kept). Review runs outside a ticket and other tickets' state are never touched.
