---
name: stick-the-landing
description: >-
  Close an mightymodels sprint: gate the push on `task_ready` and a landing `contract_run`, push, open the PR
  with a checked body, have gitty-up watch CI, and route each failing check as a recorded C task
  (mechanical fixes to an engineer residual, then architect once; non-obvious causes to
  whats-broken), re-running the landing contract at every new HEAD before re-pushing.
  On green, ask through AskUserQuestion whether to review now (review-circus) or hand off (baton-pass).
  Not for Jira sprint operations, not the review itself
  (review-circus), and not for mid-sprint work (agents-assemble owns the loop).
when_to_use: >-
  Only the user starts it, when the
  sprint's tasks are done: "finish the sprint", "wrap up the ticket", "push and open the PR",
  "get the PR open", "ship it up".
argument-hint: "[ticket-slug]"
disable-model-invocation: true
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_mighty-mcp__task_ready
  - mcp__plugin_mightymodels_mighty-mcp__task_start
  - mcp__plugin_mightymodels_mighty-mcp__task_verify
  - mcp__plugin_mightymodels_mighty-mcp__task_mark
  - mcp__plugin_mightymodels_mighty-mcp__task_show
  - mcp__plugin_mightymodels_mighty-mcp__contract_run
  - mcp__plugin_mightymodels_mighty-mcp__contract_status
---

# stick-the-landing

The bridge from "work done" to "work reviewable". It is its own stage so the user gets a look
between the sprint's last commit and anything public, and so CI failures are routed by cause,
not handled by whoever is cheapest.

Run from the repository root. Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}` in this file as
an absolute path:

- `task_ready`, `task_start`, `task_verify`, `task_mark` and `task_show` for task state.
- `contract_run` with phase `landing` to run the contract commands, and `contract_status` to read them.
- `python3 "${CLAUDE_PLUGIN_ROOT}/skills/open-ticket/scripts/humanize_tracker_body.py"` for the PR body.

Dispatch workers through prompting-subagents. Models are the fixed aliases `subagent-models`
lists, never memory.

**Argument:** the ticket's slug, given when the skill was started: "$ARGUMENTS". Empty quotes mean
none was given, and the ticket is the session's active one.

## 1. Gate

`REPORT.md` must exist: agents-assemble writes it as its last act, so its absence means the
loop stopped early. Say so and stop rather than papering over it. Then call `task_ready` with
the `slug`. It answers `ready` only when a plan task has been started, every plan task is
verified or superseded, and no C or R task is failed or blocked; otherwise it answers
`not ready` and lists the reasons. It also answers `not ready` while a live command has no
passing receipt at HEAD, or while no live `L*` command exists. Route by reason. When the only
reasons are receipts not passing at HEAD, run the landing contract as the next paragraph
describes, once, and call `task_ready` again. When the reason is the missing `L*` command, say so
and send the user back to game-plan. Any other reason is the loop's unfinished work: list the
reasons and send the user back to agents-assemble.

Run the landing contract with `contract_run`, the `slug` and phase `landing`, leaving `ids`
out so every live command runs. Only the primary holds this tool, because a hook denies it to
subagents. A run longer than about two minutes moves to the background: wait for its result, and
do not treat the notice that it moved as a pass. The push hold lifts when at least one live `L*`
command exists and every live command passes at HEAD; a ticket with no `L*` command cannot
land, so say so and send the user back to game-plan. Nothing is pushed on old evidence.

## 2. Push and open the PR

The primary pushes the branch. The main-thread hook refuses a `git push` while the ticket is unclosed unless no plan task is open, at least one live `L*` command exists, and every live command has a passing landing-phase receipt at HEAD, so when it refuses, close what it names, run step 1's `contract_run` again and push. A rejected push is reported and the skill stops; never force-push around it.

Write the PR body to `.mightymodels/SLUG/pr-body.md`: the repository's pull request template
(`.github/pull_request_template.md` or `.github/PULL_REQUEST_TEMPLATE/`) filled from REPORT.md,
linking the issue (`Closes #N` for a GitHub issue; the Jira key where the repository's
convention puts it). Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/open-ticket/scripts/humanize_tracker_body.py" fix .mightymodels/SLUG/pr-body.md --shape comment
```

Reword what `fix` reports, then run `check` with the same shape until it exits 0. Open the PR
with `gh pr create --body-file .mightymodels/SLUG/pr-body.md`. When `gh` is unavailable or
fails, surface the exact command and stop; CI watching resumes once the PR exists.

## 3. Watch CI

Dispatch gitty-up with the PR number and nothing else ("Watch PR 214."); it resolves the rest
itself and never touches code. Its report is `pass`, `fail` with per-check findings and log
tails, or `error`. An `error` (no checks, still pending, unresolvable PR) is the user's news:
never treated as a pass, re-watched at most once.

## 4. Route each failing check

One C task per failing check (`C1`, `C2`, ...); checks that fail on the same log line share
one. Apply the log-tail test: *can the fix be stated as one Fix:/Verify: line from the log
tail alone?*

- **Yes, mechanical** (lint rule, formatter drift, missing import, a trivially wrong
  assertion). Record the attempt with `task_start`, then dispatch an **engineer** with the residual variant of its template,
  Fix:/Verify: verbatim, with SLUG, `C1` as the task id and the check's name as the finding:

  The call carries SLUG, `C1` as the task id, `by` `engineer`, `owned` the files the log tail
  names and `acceptance` the criterion ids.

  When a local command reproduces the check, it is the Verify line: the engineer runs it in
  sandboxed Bash and the output is cited in `task_verify`. Otherwise the Verify line is the CI
  check itself, proven after the re-push.

- **No, non-obvious** (a behavioral failure, a flake that is not obviously a flake, anything
  where the cause would be a guess). Invoke **whats-broken**; the phased protocol exists so
  the cheapest worker does not symptom-patch CI into a worse state. Its fix dispatch is the C
  task's engineer attempt, recorded with `task_start` the same way.

## 5. Re-prove, then re-push

A fix commit moves HEAD, so every receipt is stale. Before any push, run `contract_run` with
phase `landing` again, as in step 1, and wait for its result, then `task_ready`. A C task still in
progress does not block `ready`, since its proof is the CI run the push starts; a failing contract
command does. When the run fails on an `I*` or `L*` command, the CI fix broke verified work:
`task_mark` the C task `failed` with the reason `"<id> regressed"`, and climb (step 6). Never push
past it.

Push, then gitty-up re-watches.

## 6. Close or climb

- **The check passes.** Close the C task on the evidence of the check it repaired, with
  `task_verify`: the `slug`, `task_id` `C1`, the fix `commit`, and `assertions` mapping `AC-1` to
  the check link from gitty-up. The commit must stay inside the owned set.

- **The check still fails**, or the engineer returns `failed` or `blocked`.
  `task_mark` with `to` `failed` or `blocked` and a `reason` (a task the gate blocked already
  is `blocked`), then the owner's question unless `auto-escalate` is on, as agents-assemble step 6
  has it, and **architect** once (`task_start` with `by` `architect`, the architect
  template with the trigger and the failing tail). The architect also failing goes to
  **whats-broken**; the task tools refuse a second architect implementation pass on its own. whats-broken's own stop rules end at the user,
  with every attempt's evidence.

After a compaction, `task_show` and `contract_status` (each with `slug`) and `gh pr view`
are the state; the conversation is not.

## 7. On green

Every check passes and `task_ready` answers `ready` and the landing run passed at the pushed HEAD. Tell the user, then
ask once through `AskUserQuestion` (up to four questions a call, two to four options each):

- **Review now**: invoke review-circus in this session. Recommended when this session runs a
  mid-tier primary and has context to spare.
- **Hand off**: invoke baton-pass, which prints the review session's prompt with review-circus
  as the skill to invoke.

## Boundaries

stick-the-landing pushes, opens the PR, and records C tasks. It never force-pushes, merges,
comments on the PR (review-circus owns that), or edits code itself: every fix is a dispatch
gated by the task tools. Every fallback (PR body drafted but not opened, push rejected, CI
`error`) is named in the closing summary.
