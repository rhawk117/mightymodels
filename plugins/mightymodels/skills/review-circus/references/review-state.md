# Review state (schema version 1)

Read before the first `review_state.py` call in a session, and before another skill reads a review run. `scripts/review_state.py` is the only writer.

## Location

With a ticket: `.mightymodels/SLUG/review/RUN/`. Without one: `.mightymodels/.runtime/reviews/RUN/`. `RUN` is the UTC start time, `YYYYMMDD-HHMMSS`. `start` adds `.mightymodels/` to the repository's local exclude file, so nothing here is ever tracked. prune-ticket archives ticket runs with the ticket.

| File              | Written by                    | Holds                                                                                                        |
| ----------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `review-run.json` | `start`, `dispose`, `resolve` | scope, base, HEAD, depth, emphasis, weights, personas, models, the user's dispositions, remediation outcomes |
| `findings.jsonl`  | `add`                         | normalized findings, append-only; the latest record per id wins                                              |
| `report.md`       | `report`                      | the full normalized report                                                                                   |
| `pr-comment.md`   | `report --shape comment`      | the abridged PR comment                                                                                      |

## Finding input

`add --run RUN` reads a JSON array. Every entry is validated before any is written; one bad entry rejects the batch.

```json
[{"sources": ["MV-3"], "severity": "High", "security": true, "kind": "defect",
  "title": "Token compared with ==", "location": "src/auth/session.py:88",
  "fix": "Use hmac.compare_digest", "verify": "uv run pytest -q tests/test_session.py"},
 {"sources": ["UB-2"], "severity": "Medium", "kind": "quality",
  "title": "Store mixes persistence and pricing", "location": "src/billing/store.py:10-140",
  "fix": "Extract PriceBook", "verify": "rg -n 'class PriceBook' src/billing",
  "evidence": {"kind": "metric", "cite": "uncle-bob-metrics.json ... D=0.71"}}]
```

- `sources`: report ids, `MV-n` or `UB-n`.
- `severity`: Critical, High, Medium, Low, or uncle-bob's Blocker (stored as Critical).
- `kind`: `defect` (default) or `quality`. Quality at Medium or above needs `evidence` (see idiom-evidence.md).
- `location`: `path:line` or `path:start-end`.
- `title`, `fix`, `verify`: required. Every text field is scanned for secrets and redacted before it is stored.

Normalization gives each finding a stable id, `F1`, `F2`, and so on. An incoming finding whose location overlaps an existing one on the same file merges into it: the sources join, the higher severity wins, and a gap of two or more levels records a `conflict` the user decides in the gate.

## Dispositions

`dispose --run RUN` reads `{"by": "user", "decisions": {"F1": {"decision": "fix"}, "F2": {"decision": "accept-risk", "reason": "..."}}}`. Decisions: `fix`, `defer` (ticketed for later), `accept-risk`, `dismiss`. The last two need a reason. Only `fix` routes to remediation.

## Outcomes and verdict

`resolve --run RUN --finding F1 --result fixed --commit SHA` (or `failed`/`blocked` with `--reason`) records remediation, only for findings the user chose to fix.

The verdict is computed, never written by hand:

- **BLOCK**: an open Critical, or an open High the user did not accept as risk.
- **MERGE WITH CONDITIONS**: anything open at Medium or above, including accepted and deferred findings.
- **CLEAR**: only Low findings remain open.

A finding is open until it is fixed or dismissed.
