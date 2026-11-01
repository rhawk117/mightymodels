---
name: prune-ticket
description: >-
  Close out a finished mightymodels unit of work: close_check refuses while live work
  remains (unverified tasks, a live whats-broken.md, undecided or unfixed review findings,
  unpushed commits), compacts the ticket's recorded state into a 30-line archive at
  .mightymodels/archives/<slug>.md with a JSON sidecar (contracts and results, decisions,
  review outcomes), marks the ticket closed, proposes cascading documentation updates as
  diffs for the user's approval, then, on explicit confirmation through AskUserQuestion,
  deletes the ticket directory.
  Not for deleting branches, closing issues, or general repo cleanup.
when_to_use: >-
  Only the user starts it, once the ticket's work has shipped: "/prune-ticket",
  "archive the ticket", "close out the mightymodels ticket", "clean up the ticket dir for X".
argument-hint: "[ticket-slug]"
disable-model-invocation: true
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_mighty-mcp__close_check
  - mcp__plugin_mightymodels_mighty-mcp__close_ticket
  - mcp__plugin_mightymodels_mighty-mcp__ticket_show
---

# prune-ticket

The lifecycle's last move, and the reason `.mightymodels/` never becomes a landfill: the unit
of deletion is the unit of work. Everything in the ticket directory was working state; what
deserves to outlive the ticket gets 30 lines in the archive, a bounded JSON record beside it,
and a place in the repository's real documentation. Nothing else survives.

`close_check` and `close_ticket` read the ticket's rows and git and answers with text; you write the archive
files and delete the directory. Read `references/archive-schema.md` before the first run.

**Argument:** the ticket's slug, given when the skill was started: "$ARGUMENTS". Empty quotes mean
none was given, and the ticket is the session's active one.

## 1. Refuse live work

Call `close_check` with the `slug`.

It answers `blocked` and lists every blocker it can see in the rows and git. Then check what it
cannot: open threads in REPORT.md, and open items in the issue (`gh issue view N`). Any blocker
from either: refuse, list exactly what blocks, stop. Pruning a live ticket does not close work,
it hides it.

## 2. Close into the archive

Write the three judgment lines the rows cannot hold (`shipped`, `pr`, `gotchas`), then call
`close_ticket`. Make `shipped` one line saying what the ticket delivered. Take it from REPORT.md and the PR, the URL from `gh pr view`, and at most three gotchas
from BATON.md, REPORT.md, and the review reports. `close_ticket` adds everything objective and returns the archive: write its Markdown to `markdown_path` and its record to `record_path`, then read
both back. The compression test: a teammate touching this area next quarter reads 30
lines and knows what happened and what to watch for.

The database holds the closing before either file exists, so a failed write is not a failed
close. `close_check` never returns the archive again: it answers only with blockers or no live work.
`close_ticket` again does, with a new `closed_at` and `head`, but it takes the first archive name whose
Markdown file is absent: with the Markdown missing it gives the same two paths, with the
Markdown written it gives `SLUG-2` paths and stores that as the archive. So retry the failed
write from the answer you hold, and call `close_ticket` again only when that answer is lost and the
Markdown file is missing.

## 3. Extract cascading documentation

Read REPORT.md and the review reports for "this changed how X works" signals: a new config
key, a changed workflow, a retired endpoint. Propose the matching updates to the repository's
real docs (AGENTS.md, README, runbooks) as diffs, applied only on the user's approval. Never
auto-commit documentation; wrong docs outlive wrong code. Do this before step 4, because the
reports are in the directory step 4 deletes.

## 4. Prune, on confirmation

`close_ticket` has no prune. This step is Bash and removes `.mightymodels/SLUG`, nothing else. List
what will go: that directory and its contents. The ticket's rows, its linked ledgers included,
stay in the database, and both archive files stay under `.mightymodels/archives/`. Ask once through
`AskUserQuestion`, one question with two options: delete the directory, or keep it. Only on a
yes, call `close_check` again, call `ticket_show` and read `status closed`, and confirm both archive files exist at the paths step 2
wrote. Any miss: stop and delete nothing, so a failed close never becomes a lost ticket. Then,
from the repository root, with `SLUG` the slug those calls accepted (the tools take only
letters, digits, `-` and `_`, starting with a letter or digit, so the path has no separator
and no `..`; a ticket named `archives` is never pruned, since that directory holds every archive):

```bash
rm -r -- .mightymodels/SLUG
```

Confirm what was removed in one line.

Nothing under `.mightymodels/`, the archives included, is tracked by git, so the prune is
never a commit.
