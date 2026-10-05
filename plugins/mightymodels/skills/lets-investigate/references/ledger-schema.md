# Ledger schema (version 1)

Read when an entry is rejected, when another skill needs to read an investigation, or before changing `scripts/ledger.py`. The script is the only writer; lets-investigate and what-we-know read through it too. baton-pass's `snapshot.py` reads the file directly by this schema, so a change here updates that reader in the same change.

## Location

One file per investigation: `.mightymodels/.runtime/investigations/ID.jsonl` under the repository root, found by walking up from the working directory to the first `.git`. Outside a repository the file goes under `~/.local/state/mightymodels/HASH/investigations/`, where `HASH` is the first 12 hex digits of the SHA-256 of the working directory. `ID` is `YYYYMMDD-slug-of-the-target`, with `-2`, `-3` appended on collision.

## Record

Every line is one JSON object:

| field        | type           | meaning                                                                                                                                                              |
| ------------ | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `schema`     | int            | always `1`; readers refuse any other value visibly                                                                                                                   |
| `seq`        | int            | position in the file, starting at 1; shown as `eN`                                                                                                                   |
| `round`      | int            | 0 for framing, then the round number; never decreases                                                                                                                |
| `kind`       | string         | `target`, `known`, `open`, `decision`, `resource`, `next`                                                                                                            |
| `text`       | string         | the entry, after secret redaction                                                                                                                                    |
| `source`     | string         | `code-scout`, `web-scout`, `user`, or `primary`                                                                                                                      |
| `cite`       | string or null | `file:line`, `URL#heading`, or a path; for `target`, the classification                                                                                              |
| `supersedes` | list of int    | earlier `seq` values this entry retires                                                                                                                              |
| `at`         | string         | UTC timestamp, ISO 8601, seconds                                                                                                                                     |
| `head`       | string or null | the commit the repository was at when the entry was written, read from `.git` (worktrees and packed refs included); null outside a repository or on an unborn branch |

## Rules the script enforces

| kind       | cite                              | allowed sources                                    |
| ---------- | --------------------------------- | -------------------------------------------------- |
| `target`   | classification                    | written only by `start`                            |
| `known`    | required                          | any                                                |
| `open`     | optional (where the answer lives) | any                                                |
| `decision` | optional                          | `user` only                                        |
| `resource` | required                          | any                                                |
| `next`     | optional                          | `code-scout`, `web-scout`, `user` (who answers it) |

- A batch is validated whole before anything is written; one bad entry rejects the batch and leaves the file untouched.
- `supersedes` may name only existing non-target entries. Retired entries stay in the file and drop out of `render`.
- `render` shows only the `next` entries of the latest round, since each round proposes its own.
- `knowns` prints a table of live `known`, `open`, `decision` and `resource` entries (filter with `--kind`, cap with `--limit`, default 40). Each row is `current` when its `head` equals the repository's HEAD now and `lead` otherwise: a lead is history to re-verify, not evidence.
- Text matching a secret pattern (private keys, AWS, GitHub, Slack and Stripe tokens, `password=`-style assignments) is replaced with `[REDACTED:kind]`; the receipt reports how many.
