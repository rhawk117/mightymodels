---
name: prune-ticket
description: >-
  Close out a finished mightymodels unit of work: archive_ticket.py refuses while live work
  remains (unverified tasks, a live whats-broken.md, undecided or unfixed review findings,
  unpushed commits), compacts the ticket's durable state into a 30-line archive at
  .mightymodels/archives/<slug>.md with a JSON sidecar (contracts and results, decisions,
  review outcomes, worker runs), marks the work unit closed, proposes cascading
  documentation updates as diffs for the user's approval, then, on explicit confirmation,
  deletes the ticket directory and the runtime state only it used. Use for "/prune-ticket",
  "archive the ticket", "close out the mightymodels ticket", "clean up the ticket dir for X".
  Not for deleting branches, closing issues, or general repo cleanup.
---

# prune-ticket

The lifecycle's last move, and the reason `.mightymodels/` never becomes a landfill: the unit
of deletion is the unit of work. Everything in the ticket directory was working state; what
deserves to outlive the ticket gets 30 lines in the archive, a bounded JSON record beside it,
and a place in the repository's real documentation. Nothing else survives.

Run `python3 BASE/scripts/archive_ticket.py` from the repository root, where `BASE` is the
`Base directory for this skill` line. Read `references/archive-schema.md` before the first run
in a session.

## 1. Refuse live work

```bash
python3 BASE/scripts/archive_ticket.py check --slug SLUG
```

It exits 1 and lists every blocker it can see in the files. Then check what it cannot: open
threads in REPORT.md, and unchecked tasks in the issue (`gh issue view N`). Any blocker from
either: refuse, list exactly what blocks, stop. Pruning a live ticket does not close work, it
hides it.

## 2. Close into the archive

Write the three judgment lines the files cannot hold, then close:

```bash
python3 BASE/scripts/archive_ticket.py close --slug SLUG <<'JSON'
{"shipped": "<what this ticket delivered, one line>", "pr": "<PR URL>",
 "gotchas": ["<what bit us, what to know before touching this area again>"]}
JSON
```

Take `shipped` from REPORT.md and the PR, the URL from `gh pr view`, and at most three gotchas
from BATON.md, REPORT.md, and the review reports. The script adds everything objective (tasks
and attempts, every contract command with its last result, ledger decisions, review outcomes
and reasons, worker run counts), writes both files, reads them back, and only then marks the
work unit closed. The compression test: a teammate touching this area next quarter reads 30
lines and knows what happened and what to watch for.

## 3. Extract cascading documentation

Read REPORT.md and the review reports for "this changed how X works" signals: a new config
key, a changed workflow, a retired endpoint. Propose the matching updates to the repository's
real docs (AGENTS.md, README, runbooks) as diffs, applied only on the user's approval. Never
auto-commit documentation; wrong docs outlive wrong code. Do this before step 4, because the
reports are in the directory step 4 deletes.

## 4. Prune, on confirmation

```bash
python3 BASE/scripts/archive_ticket.py prune --slug SLUG
```

Without `--confirm` it only lists what would go: the ticket directory, each linked ledger no
other ticket links, and this ticket's worker receipts. Show that list and ask once through the
ask-user dialog. Only on a yes, run it again with `--confirm`. It refuses unless the unit is
closed and both archive files read back, so a failed close never becomes a lost ticket.
Confirm what was removed in one line.

Nothing under `.mightymodels/`, the archives included, is tracked by git, so the prune is
never a commit.
