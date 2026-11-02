---
name: ask-an-adult
description: >-
  Escalate a stuck decision to the wingman advisor and act on what comes back. Builds the
  escalation packet, dispatches wingman, then puts wingman's questions to the
  user through `AskUserQuestion` before any work resumes. Not for retrieving facts (send a
  scout), not for work you can simply do, and not for confirming a plan you have
  already committed to.
when_to_use: >-
  Use when the user says they want a second opinion, when they invoke
  /ask-an-adult, or when the session has stalled on a judgment call - two
  defensible options, a hard-to-reverse choice, conflicting scout reports, a
  failure that survived two attempts, or a guess about user intent. Also use when whats-broken
  ends its phases with a judgment call between defensible options still open, and when any model
  does not know what to do next.
allowed-tools:
  - AskUserQuestion
---

# ask-an-adult

`wingman` is a one-shot advisor on the ticket's alias (`fable`). It holds no tool, so it cannot
read the ticket, a file or anything else: the packet you send is its only evidence, and the
ticket's text travels in it. The quality of its answer is capped
by the quality of the packet you send it, and a thin packet wastes a frontier
turn.

## When to spend it

Escalate when the decision is **genuinely undecidable from what you have**:

- Two options are both defensible and you cannot separate them.
- The choice is expensive to reverse - schema, public interface, dependency,
  deletion.
- Scout reports conflict with each other or with the plan.
- The same failure has survived two attempts.
- You are about to guess at what the user wants.
- whats-broken has finished its phases and a judgment call between defensible options remains.
- You do not know what to do next, whichever model you are.

Do not escalate to have a plan blessed, to retrieve a fact a scout can fetch, to
re-open a decision the user already made, or a second time on the same packet.

## Build the packet

Fill prompting-subagents' wingman template:
the decision in one sentence, each option with its cost, the ticket's text, every fact and
every assumption marked as one, constraints, what was tried, and your lean. Missing sections are
the usual reason wingman comes back at low confidence.

Wingman can read nothing and call nothing, so a path, a command or a link in the packet is a dead
end for it. Carry the text itself: for each fact, the quoted lines, the command's output or the
page's passage, with its citation beside it as provenance only. Never write "see `src/queue.py`"
or "run the tests"; paste what the file says and what the run printed.

When a ticket is active, the `<ticket>` section carries these fields of `ticket.yml`, verbatim:
`task`, `summary`, every `context` line, `companion-docs` and `handoff-context`. Leave
`subagent-models`, `triaged-at` and `investigations` out, because no decision turns on them. With
no active ticket, write `none`.

State your lean honestly. wingman is instructed to form its own view first and to lead with
disagreement, so hiding your preference buys nothing and costs the advisor a useful signal.

Run the template's ten-second checklist, then send the packet to `mightymodels:triage:wingman` through the `Agent` tool, its `model` the ticket's alias. Do not
paraphrase file contents you have not read, and do not summarize scout findings into
conclusions: pass each finding through as it came back, with the text it cites. While the ticket has a task that is
blocked or failed, or with the architect after either, and its `auto-escalate` is off, put the block
to the user before you send the packet: the dispatch hook answers this dispatch with `ask` and the
block's reasons.

## Act on the report

wingman returns a `<report agent="wingman">` block. Handle it in this order:

1. **Read `<verdict>` first.** If wingman disagrees with your lean, the
   disagreement is the first sentence. Do not proceed with your original plan
   without addressing it.
2. **Check `<confidence>`.** At `low`, the recommendation is provisional -
   resolve `<missing>` before acting on it.
3. **Run `<user_questions>` immediately.** Put wingman's questions to the user through
   `AskUserQuestion` (up to four questions a call, two to four options each), using the
   options it supplied. This is the point of the call.
4. **Dispatch scouts for `<missing>` items marked `scout`:** code-scout for repository
   facts, web-scout for external documentation. Do those in parallel
   with the user's answer where possible.
5. **Carry `<verify>` into the work.** It is the acceptance criterion for
   whatever gets built next.

Surface `<verdict>`, `<confidence>`, and `<user_questions>` to the user verbatim.
Summarizing an advisor whose whole value is its reasoning defeats the call.

The user decides; this skill is the only tie-break path. wingman's verdict alone is never the
user's answer. When the user explicitly defers to it ("you pick", "go with wingman"), that
deferral is the user's answer: adopt wingman's verdict, say in chat that the user deferred to it,
and record it as described below. Do not escalate the same packet again.

## Record it

The user's answers to wingman's questions go through `AskUserQuestion`, and the recorder hook on
that tool writes each answer, verbatim, as a decision in the ledger or ticket the session is
pointed at. Write nothing by hand: a second entry would record the same answer twice. If the
user settles the choice in chat instead of the dialog, nothing records it, so put the choice to
them again through `AskUserQuestion` before work resumes. This includes the user's deferral to wingman's
recommendation: it is a choice made in chat, which has no writer, so confirm it through
`AskUserQuestion` so the recorder takes it. With no investigation or ticket in
the session, nothing is persisted; baton-pass hands the settled decisions on when the session
ends.
