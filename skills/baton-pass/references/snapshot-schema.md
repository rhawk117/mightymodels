# Snapshot schema

Read before another component writes a table `snapshot_take` reads, and when a snapshot carries warnings. The snapshot is objective state, read from the database and git; BATON.md adds only the writer's judgment, which no table holds.

## Output

`snapshot_take` writes no file. Its answer holds `record` (the JSON below), `markdown`, and the two paths `record_path` and `markdown_path`, which are `.mightymodels/SLUG/handoffs/snapshot.json` and `snapshot.md` relative to the repository root. The agent writes both whole on every run; never tracked by git. Each list holds at most `limit` entries (default 20, at most 100), the most recent kept, except `tasks`, which lists every task. The changed paths in `repository` are cut to `limit` too; `dirty_count` is not.

| Key                           | Source                                                    | Holds                                                                                                         |
| ----------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `ticket`                      | `tickets` row                                             | summary, status, scope, tracker                                                                               |
| `repository`                  | git: branch, HEAD, `status --porcelain`                   | branch, HEAD, count and list of changed paths                                                                 |
| `tasks`                       | `tasks`, `task_attempts` rows | every started task with status, attempts, reasons |
| `decisions`, `open_questions` | `ledger_entries` of the linked investigations             | live `decision` and `open` entries, superseded ones dropped, each with its investigation and entry under `from` |
| `do_not_retry`                | `task_transitions` rows                                   | transitions into `failed` or `blocked`, with the reason and HEAD                                              |
| `review`                      | the latest `review_runs` row and its findings            | run, depth, finding count, undecided ids, remediation still open, non-fix decisions with reasons              |
| `warnings`                    | the reader                                                | git not consulted (no git binary, or not a repository), linked investigations with no ledger                  |

A section with nothing to show reads as one line in the Markdown saying so. With no git, `repository` is empty and a warning says why.

## Writers of what it reads

The snapshot reads rows other tools own. `ticket_*` writes `tickets`, and `task_*` (in progress) and `close_ticket` (closed) move its status; `task_*` writes the task rows; `investigation_*` writes `ledger_entries`, and the AskUserQuestion recorder hook writes the `decision` ones from the user; `review_*` writes the review rows. The row shapes are the contract, so a change to one of them updates this reader in the same change.
