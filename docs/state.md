# Ticket state: the .mightymodels/ directory

Everything a ticket knows lives in one directory named after it. The design rule is sparseness:
files exist because a named consumer reads them, each file class has exactly one writer, and
`/prune-ticket` deletes the whole directory when the work merges. The unit of deletion is the
unit of work, which is what stops working state from turning into a landfill of stale evidence.

## Layout of a live ticket

```text
.mightymodels/
├── <task-slug>/
│   ├── ticket.yml                source of truth: scope, routing, companion docs
│   ├── plan.md                   game-plan ramp only; high-level, citation-free
│   ├── issue-body.md             local draft, or the issue when no forge issue exists
│   ├── handoffs/SPRINT.md        thin session bootstrap
│   ├── handoffs/REVIEW.md        thin review-session bootstrap
│   ├── briefs/task-NN.md         two halves, at most 80 lines
│   ├── review/MERGE-VADER-REPORT.md
│   ├── review/UNCLE-BOB-REPORT.md
│   ├── whats-broken.md           only while a debug is live
│   └── REPORT.md                 sprint summary, at most 50 lines
└── archives/<task-slug>.md       at most 30 lines, written by prune-ticket
```

## The state database

The rows behind a ticket are not in this directory: the staged ticket, its tasks, the
verification contract and its receipts, review runs, investigation ledgers, crashouts and
closings. They are in one SQLite file, `mightymodels.db`, in the plugin data directory, the
directory Claude Code names in `CLAUDE_PLUGIN_DATA` for the plugin's state server. One file
serves every repository. Each row carries a repository key, the `owner/name` of the origin remote
or, with no origin, a hash of the checkout's toplevel path, and a read finds only the rows of the
repository it runs in. `.mightymodels/` itself sits at the git toplevel, whichever directory the
session started in.

A command run through the Bash tool does not get `CLAUDE_PLUGIN_DATA`. The plugin's SessionStart
hook exports the same directory as `MIGHTYMODELS_DATA_DIR`, and `mightymodels verify run` reads
that one. With its variable unset, or outside a git work tree, the server answers every tool call
with what is missing, and `verify run` exits 2 with the same on standard error.

This breaks with earlier versions, which kept the database inside the repository, under
`.mightymodels/`. That file is not read, not imported and not changed, so state recorded in it
does not carry over: stage the ticket again. The old file can be deleted. The new file is stamped
with a schema version, and a file with another stamp is refused by name instead of read.

## ticket.yml

Written once by open-ticket through the `ticket` tool's `write`, from the interview answers, then
hand-tweaked by the user. Every later session reads it before doing anything else.

```yaml
task: rate-limit # directory name under .mightymodels/
summary: requests over the cap return 500 instead of 429
triaged-at: 2026-08-20T14:02:00Z
context:
  - the limiter is keyed per API token, not per IP
companion-docs:
  issue-number: 214
  reference-urls:
    - docs.example.com/rate-limiting # external docs from triage only
subagent-models:
  primary-agent: null
  code-scout: haiku
  web-scout: haiku
  qualitylens: haiku
  engineer: sonnet # sonnet at every scope
  architect: sonnet # derived: large scope would pull opus
  gitty-up: haiku
  wingman: opus
  merge-vader-reviewer: opus
  uncle-bob-reviewer: sonnet
handoff-context:
  scope: sm # sm | med | large
  plan-first: false # true when a compaction is expected
  branch-name: fix/rate-limit
  worktrees-okay: false
investigations:
  - rate-limit-ledger-id # lets-investigate ids this ticket came from
```

Three derivation rules matter day to day. The engineer is `sonnet` at every scope, and the ticket
value is the default for every task; the primary may bump one gnarly task a tier at dispatch,
logging the reason in that task's ASKED stanza. The architect comes from the scope answer: `large`
gives `opus`, `sm` or `med` gives `sonnet`. `plan-first: true` means the next
session writes `plan.md` before any dispatch and the SPRINT.md handoff carries the switch-models
reminder.

The schema is deliberately closed: no key enters it without a named consumer in the flow. A
`review-weight` block existed briefly and was cut for exactly that reason.

## Handoffs stay thin

`SPRINT.md` and `REVIEW.md` contain zero facts that already live in `ticket.yml` or the issue.
They are a bootstrap pointer: read the ticket, read issue N, here is your role, invoke this
skill. Duplicated facts drift, and the next session reads `ticket.yml` first anyway.

## Briefs

`briefs/task-NN.md` holds the two-half contract for one task. The primary writes the ASKED half
at dispatch; the engineer appends the DONE half on completion; a scout verifies one against the
other. The 80-line cap is load-bearing: a brief that needs more space is a task that should have
been split. Field-level detail is in `plugins/mightymodels/skills/agents-assemble/references/contracts.md`.

## Reports and reviews

`REPORT.md` closes a sprint in at most 50 lines: what shipped, what deviated, what remains.
Review reports land under `review/` so they live and die with their ticket instead of littering
the repo root; both review skills fall back to the repo root with an ignore guard when no active
ticket exists, which keeps them usable outside mightymodels repos.

`whats-broken.md` exists only while a debug is live. It carries the current falsifiable
hypothesis and its test, gets regenerated per attempt, and its presence blocks `prune-ticket`.

## Archives and pruning

`/prune-ticket` compresses a finished ticket into `archives/<slug>.md`: what shipped, the PR
link, key decisions, and any gotcha the next person would want. Thirty lines is the cap, and the
point. During pruning the skill also proposes cascading documentation updates as diffs, README
claims the change invalidated, for the user's approval, then deletes the ticket directory.

## Git hygiene

Ticket creation runs an idempotent ignore ritual:

```bash
git check-ignore -q .mightymodels 2>/dev/null || echo '.mightymodels/' >> .git/info/exclude
```

`info/exclude` is local and needs no commit, and it is the safer default: `briefs/` and
`review/` carry raw command output that can hold secrets, so local-only exclusion means a
careless `git add -A` cannot ship them. A team adopting mightymodels can promote the entry to a
committed `.gitignore`; when tracking is wanted, track `archives/` and `*/ticket.yml` only.

## The canonical definitions

This page orients; the references define.
`plugins/mightymodels/skills/open-ticket/references/ticket-schema.md` is the schema with its
derivation rules, `plugins/mightymodels/skills/open-ticket/references/mightymodels-dir.md`
is the layout with the writer/reader matrix, and
`plugins/mightymodels/skills/agents-assemble/references/contracts.md` holds the severity table
and verdict vocabularies. Agents read those files; nothing reads this
one.
