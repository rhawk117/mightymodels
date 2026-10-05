---
name: baton-pass
description: >-
  Hand the current session to the next one without losing what this session learned. Works
  from an active ticket (mid-sprint, or after stick-the-landing went green and review is
  next) or from a session with no ticket at all. Writes an objective snapshot from the
  durable files first (snapshot.py: tasks, checks at HEAD, ledger decisions, failed
  attempts, review state, worker receipts), runs what-we-know in interactive mode, asks in one
  ask-user dialog what the next session should focus on and what to do with uncommitted work,
  records new user decisions in the ledger, then writes handoffs/BATON.md with only what no
  file holds. With no ticket it runs open-ticket first. Ends by printing the next session's
  opening prompt in chat. Use for "pass the baton", "hand this off to a fresh session", "I'm
  about to compact", "carry this over", "hand off to review". Not a ticket for work not yet
  started from a clean triage (open-ticket directly).
---

# baton-pass

A session that ends mid-work leaves two kinds of knowledge behind. One kind is already in
artifacts: ticket.yml, work-unit.json, the ledger, the verification receipts, the task
transitions, the review run, the commits. The other kind is only in this conversation: the
approach that failed before it was ever recorded, the gotcha that cost an hour, the thread
the user said to park. The next agent either receives that second kind or spends its first
hour re-deriving it, and it will re-derive some of it wrong.

The first kind is materialized by a script, not recalled: `snapshot.py` reads the durable
files and writes `handoffs/snapshot.json` and `snapshot.md`. BATON.md then carries the second
kind and only the second kind. Run it as `python3 BASE/scripts/snapshot.py write --slug SLUG`
from the repository root, where `BASE` is the `Base directory for this skill` line; read
`references/snapshot-schema.md` before the first run in a session.

<important>Invoke `prompting-subagents` before the first dispatch.</important>

## 1. Establish the state

Two entry states, decided by whether `.mightymodels/<slug>/ticket.yml` exists for the work in
progress.

- **Active ticket.** Write the snapshot and read `snapshot.md`: tasks and their attempts,
  checks at HEAD, decisions and open questions from the ledger, failed attempts, review
  state, worker receipts, branch, HEAD, and changed paths. Then read ticket.yml, the
  checklist, and the in-flight brief. Durable-before-advance applies: a commit with no DONE
  half is an incomplete task, and it is written down as one, not as "nearly done".
- **No ticket.** The state is the conversation: what was being worked on, what has been
  established, and what has changed on disk. Run `git status` to find out what this session
  touched.

Then invoke `what-we-know` in interactive mode, saying so explicitly in the dispatch so the
presence of a `briefs/` directory does not flip it into sprint mode. Its knowns table and
uncertainties are the evidence base; the interactive dialog is where uncertainties the user
can settle get settled now rather than inherited.

## 2. Ask what the next session is for

One ask-user dialog, two questions, options drawn from the state rather than generic:

**Focus.** Derived from what is open: continue the in-flight task; start the next unchecked
task; take a specific open thread the session surfaced (name it); re-plan because the picture
changed; land it (every task verified: stick-the-landing); review it (stick-the-landing
handed off on green: review-circus); something else. One recommended, with the reason in the
parenthetical.

**Uncommitted work**, only when the tree is dirty: commit as a WIP on the branch; stash with a
named message; leave it in place and say so in the baton. Recommend the commit; an uncommitted
diff is the least durable thing a session can leave.

Act on the second answer before writing anything else. The baton describes the tree as it is
after that action, and a baton that describes a stash that was never made is worse than none.

Then record every user decision made this session that the ledger does not already hold, as
a `decision` entry from `user` in the ticket's linked investigation
(`python3 BASE/../lets-investigate/scripts/ledger.py add --id ID --round N`). A decision in
the ledger reaches the next session through the snapshot; one only in the baton is one more
line to drift.

## 3. Prepare the ticket directory

**Active ticket.** Write the snapshot again, so it reflects the tree after the uncommitted-work
action and the decisions just recorded:

```bash
python3 BASE/scripts/snapshot.py write --slug SLUG
```

If it fails, stop: say what failed and do not print a next-session prompt. A handoff that
claims to be ready while its objective half is missing is the failure this skill exists to
prevent.

Then write `handoffs/BATON.md`, 40 lines or fewer, and refresh the `context:` lines in
ticket.yml with any decision the next session cannot afford to lose (three to six lines
total, no `file:line`). The baton carries only what no file holds: a task state, a check, a
ledger decision, a failed attempt `task_state.py` recorded, a passing contract command, or a
review decision is already in the snapshot, and repeating it here is a copy that drifts.

```markdown
# Baton for <slug>

Focus: <the user's answer, one line>
In flight: <task, brief path, DONE half present or absent>; tree <clean | WIP commit sha | stash name>

## Do not retry
- <approach never recorded as a task attempt> | failed because: <one line>

## Works
- <exact command outside the verification contract> | for: <what it proves or sets up>

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
since the dead ends and working commands from this session are not part of a triage rollup.

## 4. Print the prompt

Build the next session's opening prompt from prompting-subagents' next-session template, then print it
in chat inside a fenced block. It is a pointer prompt: read ticket.yml, read the issue or the
checklist, read `handoffs/snapshot.md`, read `handoffs/BATON.md`, invoke `prompting-subagents`,
then the one skill to invoke for the focus (agents-assemble to continue or start a task;
game-plan to re-plan; stick-the-landing to land; review-circus to review; the ramp per the
routing table for a freshly prepared ticket). The snapshot is a picture of the moment it was
written; the next session re-runs `task_state.py show` and `verification.py status` before
acting on it. It carries the focus line verbatim and
nothing else that lives in a file, so it cannot drift from them.

Print it after the baton is written, never before. The prompt is the last thing this session
does, and a prompt that names a file that does not exist yet is the failure this ordering
prevents.

## Boundaries

Writes `handoffs/snapshot.json`, `snapshot.md`, `BATON.md`, user decisions into the linked
ledger, the `context:` lines of ticket.yml, and whatever the user chose for uncommitted work;
through open-ticket, the ticket directory when none existed. After
refreshing ticket.yml `context`, run open-ticket's `ticket_state.py validate` so the edit
stays inside the schema's subset. Never
checks a task's box, appends a DONE half, or writes REPORT.md; those belong to the loop and
the engineer, and a baton that closes a task the loop did not verify is a lie the next
session inherits.
