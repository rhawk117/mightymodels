---
name: baton-pass
description: >-
  Hand the current session to the next one without losing what this session learned. Works
  from an active ticket (mid-sprint, or after stick-the-landing went green and review is
  next) or from a session with no ticket at all. Writes an objective snapshot from the
  recorded state first (the snapshot tool: tasks, ledger decisions, failed
  attempts, review state), runs what-we-know in interactive mode, asks in one
  AskUserQuestion call what the next session should focus on and what to do with uncommitted
  work, then writes handoffs/BATON.md with the writer's judgment, which no
  file holds. With no ticket it runs open-ticket first. Ends by printing the next session's
  opening prompt in chat. Not a ticket for work not yet
  started from a clean triage (open-ticket directly).
when_to_use: >-
  Use for "pass the baton", "hand this off to a fresh session", "I'm
  about to compact", "carry this over", "hand off to review".
argument-hint: "[ticket-slug]"
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_mighty-mcp__snapshot_take
  - mcp__plugin_mightymodels_mighty-mcp__ticket_update_context
---

# baton-pass

A session that ends mid-work leaves two kinds of knowledge behind. One kind is already in
artifacts: ticket.yml, the ticket's rows, the ledger, the verification receipts, the task
transitions, the review run, the commits. The other kind is only in this conversation: the
approach that failed before it was ever recorded, the gotcha that cost an hour, the thread
the user said to park. The next agent either receives that second kind or spends its first
hour re-deriving it, and it will re-derive some of it wrong.

The first kind is materialized by a tool, not recalled: `snapshot` reads the ticket's rows and
git and returns the record and its Markdown, and you write them to `handoffs/snapshot.json` and
`snapshot.md`. BATON.md then carries the second kind and only the second kind. Call
`snapshot_take` with the `slug`, then write the record to the `record_path` the answer gives and
the Markdown to its `markdown_path`. Read `references/snapshot-schema.md` before the first run in a session.

<important>Invoke `prompting-subagents` before the first dispatch.</important>

## 1. Establish the state

Two entry states, decided by whether `.mightymodels/<slug>/ticket.yml` exists for the work in
progress.

**Argument:** the ticket's slug, given when the skill was started: "$ARGUMENTS". Empty quotes mean
none was given, and the work in progress decides which ticket, if any.

- **Active ticket.** Take the snapshot, write both files and read `snapshot.md`: tasks and
  their attempts, decisions and open questions from the ledger, failed
  attempts, review state, branch, HEAD, and changed paths. Then read ticket.yml, the issue's
  task list (or the plan), and the in-flight brief. Durable-before-advance applies: a commit with no DONE
  half is an incomplete task, and it is written down as one, not as "nearly done".
- **No ticket.** The state is the conversation: what was being worked on, what has been
  established, and what has changed on disk. Run `git status` to find out what this session
  touched.

Then invoke `what-we-know` in interactive mode, saying so explicitly in the dispatch so the
presence of a `briefs/` directory does not flip it into sprint mode. Its knowns table and
uncertainties are the evidence base; the interactive dialog is where uncertainties the user
can settle get settled now rather than inherited.

## 2. Ask what the next session is for

One `AskUserQuestion` call, two questions, options drawn from the state rather than generic:

**Focus.** Derived from what is open: continue the in-flight task; start the next task not
yet verified; take a specific open thread the session surfaced (name it); re-plan because the picture
changed; land it (every task verified: stick-the-landing); review it (stick-the-landing
handed off on green: review-circus); something else. A question takes two to four options, so
offer the ones the state supports, one recommended with the reason in the parenthetical; the
user can type any other.

**Uncommitted work**, only when the tree is dirty: commit as a WIP on the branch; stash with a
named message; leave it in place and say so in the baton. Recommend the commit; an uncommitted
diff is the least durable thing a session can leave.

Act on the second answer before writing anything else. The baton describes the tree as it is
after that action, and a baton that describes a stash that was never made is worse than none.

Write no decision entry by hand. The recorder hook on `AskUserQuestion` already stored every
answer the user gave in a dialog, including the two just given, but only if the session was
pointed at a ledger or ticket when it was given; the snapshot carries those to the next session.
In a session with no ticket and no pointer it stored nothing, so those decisions go in
BATON.md. A choice
the user made only in chat has no writer: if it matters to the next session, put it to them
through `AskUserQuestion` now, so the recorder takes it. One only in the baton is one more line
to drift.

## 3. Prepare the ticket directory

**Active ticket.** Call `snapshot_take` again and write both files
again, so they reflect the tree after the uncommitted-work action and the decisions just
recorded.

If the call or a write fails, stop: say what failed and do not print a next-session prompt. A
handoff that claims to be ready while its objective half is missing is the failure this skill
exists to prevent.

Then read `scratchpad.md` in the ticket directory if it exists. It is the primary's free-form
working notes: only the primary writes it, and it is deleted at prune with the ticket directory. Lift
what matters from it into BATON.md; the scratchpad itself is not handed over.

Then write `handoffs/BATON.md`, 80 lines or fewer, and refresh the `context:` lines in
ticket.yml with any decision the next session cannot afford to lose (three to six lines
total, no `file:line`). The baton carries only what no file holds, and what no file holds is
your judgment: which reports you did not trust and why, what you saw yourself against what a
worker told you, and what you decided that no tool stored. A task state, a ledger decision, a
failed attempt `failed_fix_record` recorded, or a review decision is already in the snapshot,
and repeating it here is a copy that drifts.

```markdown
# Baton for <slug>

Focus: <the user's answer, one line>
In flight: <task, brief path, DONE half present or absent>; tree <clean | WIP commit sha | stash name>

## What I distrust and why
- <report, claim or result I did not accept> | why: <one line>

## First-hand and reported
- saw myself: <what I ran or read> | reported by a worker: <what I took on its word>

## Decisions with no writer
- <decision made in this session and recorded nowhere else> | why: <one line>

## Next check
- <the one check to run first> | expect: <result>

## Do not retry
- <approach never recorded as a task attempt> | failed because: <one line>

## Gotchas
- <what cost time> | so: <what to do instead>

## Parked
- <thread> | why parked: <one line> | revisit when: <signal>
```

Every line is a fact from this session with its origin. "Consider refactoring X" is not a
baton line; "X was refactored and reverted because the test at Y depends on the old shape" is.
A next agent that receives advice reasons about it; one that receives facts acts on them. An
empty section is omitted, not padded.

**No ticket.** Invoke `open-ticket` with the focus answer as the summary and the next step
already decided (hand off), so it does not ask what comes next. It runs the
interview for whatever the conversation has not answered, rolls the what-we-know findings
into the issue body and ticket.yml `context`, and creates the branch or records the current
checkout. When it returns, write the snapshot, then `handoffs/BATON.md` in the same shape,
since the dead ends and judgment from this session are not part of a triage rollup.

## 4. Print the prompt

Build the next session's opening prompt from prompting-subagents' next-session template, then print it
in chat inside a fenced block. It is a pointer prompt: read ticket.yml, read the issue's task
list or the plan, read `handoffs/snapshot.md`, read `handoffs/BATON.md`, invoke `prompting-subagents`,
then the one skill to invoke for the focus (agents-assemble to continue or start a task;
game-plan to re-plan; review-circus to review; the ramp per the
routing table for a freshly prepared ticket). To land, the prompt names no skill to invoke: only
the user can start stick-the-landing, so the prompt tells the next session to hand the user
`/mightymodels:stick-the-landing <slug>`. The snapshot is a picture of the moment it was
written; the next session calls `task_show` and `contract_status` before
acting on it. It carries the focus line verbatim and
nothing else that lives in a file, so it cannot drift from them.

Print it after the baton is written, never before. The prompt is the last thing this session
does, and a prompt that names a file that does not exist yet is the failure this ordering
prevents.

## Boundaries

Writes `handoffs/snapshot.json`, `snapshot.md`, `BATON.md`, the `context:` lines of ticket.yml,
and whatever the user chose for uncommitted work;
through open-ticket, the ticket directory when none existed. Refresh ticket.yml `context` with
`ticket_update_context` (it replaces the whole list). Never marks a task verified, appends a DONE half, or writes
REPORT.md; those belong to the loop and the engineer, and a baton that closes a task the loop
did not verify is a lie the next session inherits.
