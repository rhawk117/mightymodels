---
name: agents-assemble
description: >-
  Use when starting, resuming, or continuing the mightymodels per-task work loop for a staged
  ticket (after game-plan or one-shot): engineer dispatch per task, contract commands run
  before judgment checks, task_state.py gating each task on receipts, citations and
  ownership, architect once on failure, whats-broken after that.
---

# agents-assemble

The per-task loop. Its whole design bet is that verification has a persisted target: the ASKED half of each brief is written *before* the engineer starts, so "done" is checkable against what was asked rather than against what got built. Read `references/contracts.md` once per session — it carries the severity table, verdict vocabularies, the two-half brief schema, and the caps this file assumes.

**Preconditions:** a staged ticket (`.mightymodels/<slug>/work-unit.json`, written by open-ticket's `ticket_state.py validate`) and an enumerable task list: the issue-body checklist (one-shot) or `plan.md` tasks (game-plan). Missing either → stop and name it; the ramps exist to produce them.

Run the scripts from the repository root: `python3 BASE/scripts/task_state.py` (this skill;
`BASE` is the `Base directory for this skill` line) and
`python3 BASE/../game-plan/scripts/verification.py` (the ticket's verification contract).

## Per task

**1. what-we-know, sprint mode.** Fresh citations for this task against current HEAD: where the change lands, what touches it, candidate `files-in-scope`. Uncertainties come back to you with blast radius; you decide ask-versus-proceed. A wrong guess confined to one file is a fix; a wrong guess across a boundary is a mess.

**2. Write the ASKED stanza.** Use prompting-subagents' engineer template; its output is the stanza. Paste it to the top of `briefs/task-NN.md` and into the dispatch. Every AC is a contract command (`Tn.AC-m`) or a checkable assertion with a location; "works correctly" is refused at write time, because an uncheckable criterion turns verification into theater. A command AC not yet in the contract goes to the user in one ask-user dialog (id and argv) and is recorded with `verification.py contract` before the dispatch; the runner will not execute anything else. Engineer tier comes from ticket.yml; bump one tier for a genuinely gnarly task, with the reason logged in the stanza.

**3. Open the attempt, then dispatch.**

```bash
python3 BASE/scripts/task_state.py start --slug SLUG --task Tn --by engineer --owned <files-in-scope>
```

The owned set recorded here is what step 5 checks the commit against, so it is the stanza's `files-in-scope`, not a guess. Then dispatch `mightymodels:engineer` with its model from ticket.yml `subagent-models` (the agent file's pin is only the headless fallback). The dispatch names the brief path; the engineer appends `## DONE` before reporting and commits; push only in remediation mode.

**4. Mechanical checks before judgment.** On `done`, run the task's contract commands at the new HEAD:

```bash
python3 BASE/../game-plan/scripts/verification.py run --slug SLUG --phase task --id Tn.AC-1 --id Tn.AC-2
```

Then one code-scout pass for the assertion ACs only, criterion by criterion, each coming back `VERIFIED` with a citation or not. An engineer report claiming `verified="true"` on a criterion the check contradicts gets called out by name; averaging a contradiction is how drift compounds. Then your own surface-level read of the diff; it is the second opinion now, not the only one.

**5. Gate the task.**

```bash
python3 BASE/scripts/task_state.py verify --slug SLUG --task Tn --commit <engineer commit> \
  --brief .mightymodels/SLUG/briefs/task-NN.md --assertion AC-2=<file:line from code-scout>
```

It passes only when every `Tn.*` contract command passed at the current HEAD, every other AC in the brief carries a citation, and the commit touched nothing outside the owned set (read from git, not from the report). It writes `work-unit.json` and `transitions.jsonl` before it prints `verified`. A `blocked` result lists why; treat it as a failed attempt.

The plugin's `completion-gate` hook already held the engineer once to its owned files, its commit, and its DONE half. A report that arrives with a `<hook_context hook="completion-gate">` block appended still has those violations open: route it as a failed attempt, whatever its status says.

**6. Route what did not verify.**

- Bounded, mechanical, one-concern residual (the gate's reasons name it) → **engineer**, residual variant of its template, Fix:/Verify: verbatim, after `task_state.py start --by engineer --owned <files the Fix touches>`.
- Engineer returns `failed` or `blocked`, or the gate blocks after its attempt → `task_state.py mark --to failed|blocked --reason ...`, then **architect** once: `task_state.py start --by architect --owned <the same owned set>` and the architect template (trigger, ASKED, mode, brief path). Architect replaces the brief's DONE half and is gated by step 5 like the engineer.
  - `scope-expansion-requested`: put the requested files to the user. On approval, `start --by architect --expanded-envelope --owned <expanded set>` and dispatch in `systemic-refactor` mode; the script allows exactly one such extra pass.
  - `replanned`: the revised ASKED becomes a new task (next free `T` id) with its own contract commands, approved like any other.
- Architect also fails → **whats-broken**. `task_state.py` refuses a second recovery pass on its own; the next attempt is never another patch, because repeated failure means the understanding is wrong.

**7. Close the task.** Durable before advance: only after `task_state.py verify` printed `verified` do you check the task's box (issue checklist or plan) and move on. A task that did not verify does not close; it routes (step 6) or escalates to the user with the gate's reasons. On recovery after a compaction, `task_state.py show --slug SLUG` and `verification.py status --slug SLUG` are the state; the conversation is not.

Review remediation from review-circus re-enters here: each selected finding is a new task or residual with its own contract commands, and an architect `diagnose-replan` result from review arrives as a revised ASKED, run through this same loop.

## Sprint end

Report the count: tasks completed, residuals fixed, anything escalated. Write `REPORT.md` (≤50 lines): what shipped per task, commits, open threads. Then **stop** — pushing and PR-opening belong to stick-the-landing, so the user gets a look between "work done" and "work public".

## Rules that keep the loop honest

Models never hardcoded: ticket.yml decides. State never lives only in the conversation: `task_state.py` and the verification receipts are what a recovered session reads. Briefs are written, never pasted wholesale into dispatches (paths travel, content doesn't). Caps are contracts: 80-line briefs, 50-line REPORT. And the loop never asks the user a question a blast-radius judgment could answer — but never guesses across a boundary either.
