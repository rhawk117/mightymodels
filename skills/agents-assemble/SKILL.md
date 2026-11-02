---
name: agents-assemble
description: >-
  Use when starting, resuming, or continuing the mightymodels per-task work loop for a staged
  ticket (after game-plan or one-shot): engineer dispatch per task, a fact-checker dispatch
  to check it, the primary comparing the two reports and recording its verdict with
  `task_verify`, architect once on failure, whats-broken after that.
when_to_use: >-
  Use for "run the loop", "start the sprint", "do the next task", "pick the sprint back up", and
  when game-plan or one-shot hands over a staged ticket.
argument-hint: "[ticket-slug]"
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_mighty-mcp__ticket_show
  - mcp__plugin_mightymodels_mighty-mcp__task_start
  - mcp__plugin_mightymodels_mighty-mcp__task_verify
  - mcp__plugin_mightymodels_mighty-mcp__task_mark
  - mcp__plugin_mightymodels_mighty-mcp__task_show
---

# agents-assemble

The per-task loop. Its design bet is that verification has a persisted target: the ASKED half of each brief is written *before* the engineer starts, so "done" is checkable against what was asked rather than against what got built. The second bet is that you are a skeptical manager, not a second implementer. Your context is the scarce resource that grounds the whole workflow, so workers do the work and the checking, and you keep each one accountable through checks and balances: the implementer's report set against the fact-checker's report. You compare the two and look further yourself only on a contradiction or on vagueness; rereading the whole diff by yourself is how your context fills with what a worker should have read. You decide the verdict and record it. Read `references/contracts.md` once per session: it carries the severity table, verdict vocabularies, the two-half brief schema, and the caps this file assumes.

**Preconditions:** a staged ticket (`ticket_show` answers; open-ticket's `ticket_validate` staged it) and an enumerable task list: the issue's task list (one-shot) or `plan.md` tasks (game-plan). Missing either → stop and name it; the ramps exist to produce them.

**Argument:** the ticket's slug, given when the skill was started: "$ARGUMENTS". Empty quotes mean none was given, and the ticket is the session's active one.

You have a scratchpad at `.mightymodels/SLUG/scratchpad.md`: free-form, yours alone to write, deleted with the ticket directory at prune. Jot what you distrust and what you saw first-hand there as you go; baton-pass lifts what matters into BATON.md.

Progress lives in the task tools: `task_show` is what a recovered session reads. Commands run in sandboxed Bash, by the workers.

## Per task

**1. what-we-know, sprint mode.** Fresh citations for this task against current HEAD: where the change lands, what touches it, candidate `files-in-scope`. Uncertainties come back to you with blast radius; you decide ask-versus-proceed. A wrong guess confined to one file is a fix; a wrong guess across a boundary is a mess.

**2. Write the ASKED stanza.** Use prompting-subagents' engineer template; its output is the stanza. Paste it to the top of `briefs/task-NN.md` and into the dispatch. Write each acceptance criterion as a plain outcome sentence a worker can check at a named place; "works correctly" is not one, because an uncheckable criterion turns verification into theater. Give the stanza a `verification:` line of the commands that prove it, which the engineer runs in sandboxed Bash and quotes in its DONE half. When game-plan saved `.mightymodels/SLUG/toolchain.md`, the `TC` lines that bind this task go verbatim in the stanza's `toolchain:` slot. The engineer's model is `sonnet`, as ticket.yml repeats; bump it one tier for a genuinely gnarly task, with the reason logged in the stanza.

**3. Open the attempt, then dispatch.**

Call `task_start` with the `slug`, the `task_id` (`T1`), `by` `engineer`, `owned` the files in scope and `acceptance` one short entry per outcome sentence of the stanza.

The owned set recorded here is what `task_verify` reports the commit against in step 5, so it is the stanza's `files-in-scope`, not a guess, and `acceptance` lists every criterion of the stanza so the tool can count them. Size is guidance: `task_start` starts every task, and its answer carries a warning above three owned files or four criteria, naming **break-it-down**. A task that draws the warning may go to break-it-down, which splits it and puts the split to the user; when the user keeps it whole, continue with the task as started. Then dispatch `mightymodels:workers:engineer` through the `Agent` tool, its `model` the engineer's fixed alias, `sonnet`, which `subagent-models` repeats. The dispatch names the brief path; the engineer appends `## DONE` before reporting and commits, and never pushes: only the primary pushes.

A task's size in the plan picks the worker: a `tiny` task (it owns exactly one file and the change is mechanical) goes to the intern, and every other size to the engineer, which may also take a tiny one. A task given to the intern is opened the same way with `by` `intern` and its one owned file, and dispatched as `mightymodels:workers:intern` on `haiku`, with prompting-subagents' intern template. The dispatch hook refuses that dispatch unless the intern has a started task and every task started for it owns exactly one file; its refusal names the engineer.

**4. Have the work checked, then compare.** On `done`, do not rerun or reread the work yourself. Dispatch `mightymodels:review:fact-checker` on `haiku`, with prompting-subagents' fact-checker template: the brief path, the slug and task id, and the commit. It reads the brief's ASKED and DONE halves, checks each acceptance criterion criterion by criterion (each coming back `VERIFIED` with a citation, `REFUTED` or `UNCHECKED`), reruns the verification commands, and reads the commit's diff for quality, rating each finding on the severity table. A command the sandbox blocks is reported to the user with the exact `!` command to run, never run with the sandbox off.

Then compare the two reports: the implementer's DONE half against the fact-checker's answer. Agreement on every criterion, with output cited, is enough. Look further only on a contradiction (an implementer claiming `verified="true"` on a criterion the check refutes, or a rerun that differs from the quoted output) or on vagueness (a criterion answered with no citation, a result with no command). Then send a narrower question to the worker that can answer it, or to code-scout, and call the contradiction out by name; averaging it is how drift compounds. Its `CLEAR`, `HOLD` and severity outcomes advise your verdict; they do not make it.

What a quality finding does to the task depends on its severity and on what it cites:

- A finding blocks only when it is Critical or High and cites both a file and line and the criterion or rule it breaks. A blocking finding, like a `REFUTED` criterion, keeps the task open: record `failed` in step 5 and route it (step 6), with the finding's line and its criterion or rule verbatim in the next ASKED.
- A Medium or Low finding does not hold the task. Record it in the brief under `## FINDINGS`, one line each (`FC-n | severity | file:line | criterion or rule | evidence`); review-circus picks it up from there.
- A finding without both the file and line and the criterion or rule is advisory whatever its severity. Record it in the same place with `advisory` in front, and it holds nothing.

**5. Record the verdict.**

Call `task_verify` with the `slug`, the `task_id`, the engineer's `commit` and your `verdict`: `verified`, `failed` or `blocked`. A `failed` or `blocked` verdict needs a `reason`, and a `verified` one takes none. The verdict is yours, not the tool's.

The answer returns the facts it found: `commit_is_head`, `base_is_ancestor` and `outside_owned`, the files the commit touched outside the owned set. They do not change the verdict; a stale commit or a file outside the owned set is yours to judge. A commit that is not HEAD, a base that is not an ancestor, or an unexpected file in `outside_owned` is a reason to look further, and a reason to record `failed` when the work is not what was asked. The brief's DONE half still has to name the commit on a `commit: <hash>` line of its own.

**6. Route what did not verify.**

- Bounded, mechanical, one-concern residual (your recorded reason or the fact-checker's blocking finding names it) → **engineer**, residual variant of its template, Fix: plus an outcome sentence, and Verify: verbatim, after `task_start` with `task_id` the next `R<n>` that `task_show` does not list, `by` `engineer`, `owned` the files the Fix touches and `acceptance` the outcome sentence the Fix is meant to produce. The dispatch carries SLUG and that `R<n>` as its task id, and the finding's own id (`FC-n`, or your recorded reason) in its own slot, never as the task id:

  A `T` task you recorded `failed` or `blocked` closes after its residual verifies: start the `T` task again and run steps 4 and 5 at the residual's commit, so its own criteria are checked at HEAD. Step 5 still wants the brief's `commit:` line to name that commit.
- Intern returns `blocked`, or you recorded `blocked` or `failed` after its attempt → a task you recorded `blocked` is already `blocked`; otherwise `task_mark` with `to` `blocked` and a `reason`; then **engineer**: `task_start` with `by` `engineer` and the same owned set and acceptance, and the engineer template with the intern's blocker in its context. The task goes to the engineer with no question to the user, and never back to the intern.
- Engineer returns `failed` or `blocked`, or you recorded `blocked` or `failed` after its attempt (an engineer's `blocked` after three failed fixes lists the hypotheses it tried; put them in the architect's ASKED so none is tried again) → a task you recorded `failed` or `blocked` is already marked; otherwise `task_mark` with `to` `failed` or `blocked` and a `reason`. Escalation is this step's: the block goes to the owner before it is escalated: read `auto_escalate` in the ticket section that `ticket_show` answers, which is off unless ticket.yml has `auto-escalate: true` under `handoff-context`. Off → one `AskUserQuestion` dialog giving the task, its status and the reasons verbatim, with two answers: give it to the architect for its one pass, or hold it for the user's instruction. Start and dispatch nothing before the answer, and on hold leave the task as marked and do what the user says. On, or the user chose the architect → **architect** once: `task_start` with `by` `architect` and the same `owned` and `acceptance` (the mode defaults to `recovery-implementation`), and the architect template (trigger, ASKED, mode, brief path). Architect replaces the brief's DONE half and is checked by steps 4 and 5 like the engineer.
  - `scope-expansion-requested`: put the requested files to the user. On approval, hand the task, still in progress, to the architect again: `task_start` with `by` `architect`, `mode` `systemic-refactor`, the expanded `owned` set and the same `acceptance`, and dispatch in that mode; the tool allows exactly one such extra pass.
  - `replanned`: one task with a revised ASKED. `task_mark` with `to` `superseded` closes the old task so `ready` can pass, and the revised ASKED becomes a new task (next free `T` id) with its own outcome sentences.
- Engineer or architect returns `too-large` (its `cuts` name where to cut), or `task_start` warns that the task is large, or a plan task is plainly several changes → **break-it-down**, with the cuts in hand when a worker gave them. A `too-large` task is not retried whole unless the user keeps it so, and the architect is not sent to shrink it. That skill shows the user the pieces and waits; only after the answer is the original superseded and the plan updated, and each piece then runs through this loop as a task of its own.
- Architect also fails → **whats-broken**, the primary's protocol (the engineer's `agent-debugging` has already spent its three fixes), with the engineer's hypotheses in its log. Only `diagnose-replan`, which edits nothing, may still start. The next attempt is never another patch, because repeated failure means the understanding is wrong.

**7. Close the task.** Durable before advance: only after you recorded `verified` with `task_verify` do you move on. A task that did not verify does not close; it routes (step 6) or escalates to the user with your reasons. On recovery after a compaction, `task_show` is the state; the conversation is not.

Review remediation from review-circus re-enters here: each selected finding is a new task or residual with its own outcome sentences, and an architect `diagnose-replan` result from review arrives as a revised ASKED, run through this same loop.

## Sprint end

Report the count: tasks completed, residuals fixed, anything escalated. Write `REPORT.md` (≤50 lines): what shipped per task, commits, open threads. Then **stop** and hand the user `/mightymodels:stick-the-landing SLUG`, which only the user can start: pushing and PR-opening belong to that skill, so the user gets a look between "work done" and "work public".

## Rules that keep the loop honest

Models are the fixed aliases `subagent-models` lists, never memory. A worker the sandbox or a permission refusal stopped reports `blocked`, and the primary never commits for it or turns the sandbox off. State never lives only in the conversation: the task tools are what a recovered session reads. Briefs are written, never pasted wholesale into dispatches (paths travel, content doesn't). Caps are contracts: 80-line briefs, 50-line REPORT. And the loop never asks the user a question a blast-radius judgment could answer, but never guesses across a boundary either.
