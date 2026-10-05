# Verification contract (schema version 1)

Read when recording or extending a contract, when a run is refused, or before another skill reads the receipts. `scripts/verification.py` is the only writer.

## Files

`.mightymodels/SLUG/verification/contract.json` and `receipts.jsonl`, next to the ticket's `work-unit.json`. Like everything under `.mightymodels/`, never tracked by git; prune-ticket archives them with the ticket.

## Contract

```json
{"schema": 1, "slug": "SLUG", "commands": {
  "T1.AC-1": {"id": "T1.AC-1", "argv": ["uv", "run", "pytest", "-q", "tests/test_queue.py"],
              "expect_exit": 0, "timeout": 300, "approved_by": "user",
              "approved_at": "2026-09-28T19:00:00+00:00", "head": "SHA"}}}
```

- **ids**: `I<n>` for invariants, `T<n>.AC-<n>` for task acceptance criteria, `C<n>.AC-<n>` for a local reproduction of a failing CI check, so `status --prefix T3.` answers "is task 3 proven".
- **argv** is a list, never a shell string: no pipes, redirection, globbing, `&&`, or variable expansion. A check that needs a pipeline belongs in a script the repository owns, and the contract runs that script.
- **expect_exit** is the exit code that proves the criterion, usually 0. It is the completion expectation, not the planning baseline: a test that does not exist yet fails at planning time and that is recorded, not refused.
- **timeout** is 1 to 3600 seconds, default 300. A hang is a failure, never a pass.
- **approval**: `contract` requires `approved_by` and stamps the time and HEAD. The skill shows the user the full id and argv list in one ask-user dialog before recording; the script cannot see the dialog, so recording without it is a skill violation, not a script bypass.
- An approved id never changes its argv; a different command gets a new id and a new approval.

## Running

`run --id ID ...` looks each id up in the contract and executes its argv, without a shell, from the repository root. `run --all` runs every approved id, which is how stick-the-landing re-proves the ticket after a CI fix moves HEAD. An id not in the contract is refused before anything runs; the caller can never pass an argv, which is what keeps the runner from being a general shell. `--phase` is `planning`, `task`, `review`, or `landing`.

## Receipts

One JSON object per run, appended: `id`, `argv`, `outcome` (`pass`, `fail`, `timeout`, `not-found`), `exit`, `duration_ms`, `stdout_tail` and `stderr_tail` (last 40 lines, at most 4000 characters), `digest` (SHA-256 of the full stdout plus stderr), `head`, `phase`, `at`, `schema`.

## Status

`status [--prefix P]` prints each matching id with its latest receipt: `pass`/`fail` with its phase when the receipt is at the current HEAD, `stale (...)` when it ran at another HEAD, `never-run` otherwise. It exits 0 only when every matching id passed at the current HEAD, which is the check the loop and the completion gate rely on.
