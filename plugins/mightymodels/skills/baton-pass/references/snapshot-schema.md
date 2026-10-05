# Snapshot schema (version 1)

Read before changing `scripts/snapshot.py`, before another component writes one of the files it reads, and when a snapshot carries warnings. The snapshot is objective, file-backed state; BATON.md adds only what no file holds.

## Output

`.mightymodels/SLUG/handoffs/snapshot.json` and `snapshot.md`, regenerated whole on every run with atomic replacement. Never tracked by git. Each list holds at most `--limit` entries (default 8), the most recent kept, except `checks`, which lists every contract command.

| Key                           | Source                                              | Holds                                                                                            |
| ----------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `ticket`                      | `work-unit.json`                                    | summary, status, scope, tracker                                                                  |
| `repository`                  | `.git` files, `git status --porcelain`              | branch, HEAD, count and list of changed paths                                                    |
| `tasks`                       | `work-unit.json` progress, contract ids             | every started task with status, attempts, reasons; contract tasks never started                  |
| `checks`                      | `verification/contract.json`, `receipts.jsonl`      | each command: `pass`/`fail`/`timeout`/`not-found` at HEAD, `stale (...)`, or `never-run`         |
| `works`                       | the same                                            | commands whose latest receipt passed, with their argv                                            |
| `decisions`, `open_questions` | linked ledgers (`.runtime/investigations/ID.jsonl`) | live `decision` and `open` entries, superseded ones dropped                                      |
| `do_not_retry`                | `transitions.jsonl`                                 | attempts that ended `failed` or `blocked`, with the reason and HEAD                              |
| `review`                      | the latest `review/RUN/`                            | run, depth, finding count, undecided ids, remediation still open, non-fix decisions with reasons |
| `answers`                     | `.runtime/decisions/receipts.jsonl`                 | this ticket's most recent ask_user answers                                                       |
| `subagents`                   | `.runtime/subagents/receipts.jsonl`                 | this ticket's most recent worker results                                                         |
| `warnings`                    | the reader                                          | missing linked ledgers, unreadable lines, unsupported versions                                   |

A source that does not exist is empty. A record whose `schema` is not 1 is skipped and named in `warnings`; nothing is guessed.

## Hook receipts

Written by the plugin's hooks (`src/mightymodels_plugin/hooks.py`), append-only and repository-scoped; the full shapes are `references/state/receipt.schema.json` at the plugin root, generated from the structs in `src/mightymodels_plugin/workflow_state.py`.

- `.mightymodels/.runtime/subagents/receipts.jsonl`, one per mightymodels worker stop (subagent-recorder): `agent`, `agent_id`, `agent_type`, `status`, `ticket`, `head`, `at`, `summary`, `stop_reason`, `evidence`, `unavailable`.
- `.mightymodels/.runtime/decisions/receipts.jsonl`, one per ask_user answer (decision-recorder): `id`, `ticket`, `head`, `at`, `session`, `question`, `answer`, `options`, `unavailable`.

`ticket` is the ticket whose `work-unit.json` names the checked-out branch, or `null` when none does; snapshot.py keeps only receipts whose `ticket` matches. `status` is the worker's own vocabulary as its report states it. `unavailable` names the fields the CLI payload did not carry; they are never inferred.

## Readers other than snapshot.py

snapshot.py reads files that other scripts own: `ledger.py`, `verification.py`, `task_state.py`, and `review_state.py` stay their only writers. The schemas those scripts document are the contract, so a change to one of them updates this reader in the same change.
