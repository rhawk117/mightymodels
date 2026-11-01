---
name: review-circus
description: >-
  Review a diff, branch, ticket, or whole codebase with the mightymodels persona reviewers. One
  AskUserQuestion gate sets depth (quick runs its reviewers on sonnet, standard and deep on opus), persona
  emphasis, and scope; the `review_*` tools record the run, `review_metrics` and qualitylens's signals tools
  measure, merge-vader and uncle-bob report, and the tool reads their reports
  and merges overlapping findings, presented by id through AskUserQuestion. Only the findings
  the user picks go to remediation, risk first, through the `task_*` tools; an abridged PR comment
  is always posted. Not for fixing CI (stick-the-landing) or mid-sprint work
  (agents-assemble).
when_to_use: >-
  Use for
  "run the review circus", "review the sprint", "full review pass", "both reviewers on this", and
  for a quick single-persona pass: "quick merge-vader on this branch", "uncle-bob this module",
  "is this safe to merge".
argument-hint: "[diff | branch | ticket <slug> | codebase]"
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_mighty-mcp__review_start
  - mcp__plugin_mightymodels_mighty-mcp__review_override
  - mcp__plugin_mightymodels_mighty-mcp__review_metrics
  - mcp__plugin_mightymodels_mighty-mcp__review_add
  - mcp__plugin_mightymodels_mighty-mcp__review_gate
  - mcp__plugin_mightymodels_mighty-mcp__review_dispose
  - mcp__plugin_mightymodels_mighty-mcp__review_report
  - mcp__plugin_mightymodels_mighty-mcp__review_resolve
  - mcp__plugin_mightymodels_mighty-mcp__task_start
  - mcp__plugin_mightymodels_mighty-mcp__task_verify
  - mcp__plugin_mightymodels_mighty-mcp__task_mark
  - mcp__plugin_mightymodels_mighty-mcp__task_show
  - mcp__plugin_mightymodels_mighty-mcp__task_ready
  - mcp__plugin_mightymodels_mighty-mcp__contract_run
---

# review-circus

Two reviewers with different worldviews, and this session's primary as the ringmaster: it
sets the profile, measures, dispatches, normalizes, and routes what the user chooses to fix.
It never reviews code itself and never invents a finding. An empty run means the reviewers
have not reported, not that the primary should improvise.

Run the commands from the repository root. `${CLAUDE_SKILL_DIR}` is this skill's directory, which
Claude Code substitutes in this file as an absolute path. Subagents do not inherit it, so every
path a dispatch carries is absolute.

- `review_start`, `review_override`, `review_add`, `review_gate`, `review_dispose`, `review_report` and `review_resolve` record the run, the findings, and the decisions.
- `review_metrics` measures structure (fan-in, fan-out, cycles, sizes) into the run directory. Only this session's primary calls it.
- Git history (churn, coupling, hotspots) is measured by qualitylens with the `signals_*` tools; the personas dispatch it, this skill does not call them.
- `task_start`, `task_verify`, `task_mark`, `task_show` and `task_ready` for remediation tasks, and `contract_run` for the landing run.

Read `references/profiles.md` and `references/review-state.md` before the first run in a
session, and `agents-assemble/references/contracts.md` for the severity table. Dispatch every
worker through prompting-subagents.

## 1. Profile

**Argument:** the scope to review (diff, branch, ticket with its slug, or codebase), given when the
skill was started: "$ARGUMENTS". Empty quotes mean none was given, and the scope is settled as
below.

The profile is the scope, the depth and the emphasis of the review. Say what each depth costs
(profiles.md): quick is one persona on sonnet, standard and deep run their reviewers on opus.
Then record the profile with `review_start`,
carrying only what the conversation has already settled. The tool puts each of `scope`, `depth`
and `emphasis` that the call leaves out to the user and starts the run with the answers:

```json
{"scope": "ticket", "slug": "SLUG", "base": "main"}
```

An answer starting `needs input` means no one could be asked through the tool: put each question
it names to the user in one `AskUserQuestion` dialog, then call again with those arguments. A scope of branch needs `base`, a scope of ticket needs `slug`, and an emphasis of custom
needs `weights`; a refusal naming one of them means: ask the user for it, then call again.

For a quick review with balanced weights, ask the user which persona and pass it as `persona`.

It answers with the run id, the run directory, and each persona's model. Every later step
names the run with `run_id`.

A run may spend one override on its heavier-weighted reviewer (the first persona, merge-vader, on equal weights), moving it to fable. Ask for it only when the user wants the strongest reviewer, with `review_override`:

```json
{"run_id": "20261005-103000"}
```

The answer names the reviewer and says to dispatch it with effort high; a second request on the run is refused. A ticket's reviewer keys change no review.

## 2. Measure

When uncle-bob is in the run, call `review_metrics` with the `run_id`. It measures the repository
into `uncle-bob-metrics.json` in the run directory and returns the path; that path goes into
uncle-bob's dispatch, because uncle-bob holds no state tool and only reads the file.

Pass `package_depth` 2 when the repository is one top-level package. When the languages are
ones it does not parse (it reads Python, JavaScript, and TypeScript), skip it and say so in
the dispatch.

At standard and deep, pick the history window the personas hand qualitylens per profiles.md
(`baseline_ref` BASE_REF for branch and ticket scope). At standard and deep, a code-scout
surface triage also runs first: diff stat, risk hotspots (auth, input handling, CI config,
dependency manifests), tests covering the changed area. Quick skips both unless the persona
names a specific gap.

## 3. Dispatch the personas

Dispatch each persona in the run, in parallel, with prompting-subagents' reviewer template
and the model the run recorded. Each persona preloads its doctrine as a skill of its own
(`becoming-merge-vader`, `becoming-uncle-bob`) and is passed no doctrine path. The packet carries
`${CLAUDE_SKILL_DIR}/references/profiles.md`, `${CLAUDE_SKILL_DIR}/references/idiom-evidence.md`,
the run directory, the depth and the persona's role (the heavier weight leads), the metrics
path `review_metrics` returned, the signals history window (which the persona hands qualitylens), and for a ticket,
ticket.yml, the issue, and the plan
(merge-vader's conformance check needs them). The `${CLAUDE_SKILL_DIR}` paths are absolute once substituted.

For a ticket, the packet also names every brief that holds a `## FINDINGS` section
(`rg --no-config -l '^## FINDINGS' .mightymodels/SLUG/briefs`): the fact-checker's Medium, Low
and advisory findings, which agents-assemble recorded when it let the task go on. A persona opens
the line of each and reports the ones that stand as findings of its own. A recorded finding no
persona confirms does not reach the gate, because `review_add` takes findings from the persona reports
and from nowhere else.

Personas gather their own evidence through code-scout and qualitylens, merge-vader through
web-scout too, and nothing else. Write each response unchanged to `RUNDIR/MERGE-VADER-REPORT.md` or
`RUNDIR/UNCLE-BOB-REPORT.md`, the files `review_add` reads. Wait for every persona in the run.

## 4. Record the reports

Call `review_add` once per persona in the run:

```json
{"run_id": "20261005-103000", "persona": "merge-vader"}
```

`review_add` reads that persona's report itself, so no step retypes a finding, and one finding it
refuses rejects the batch with the reason and stores nothing. A quality finding at Medium or
above needs typed evidence (idiom-evidence.md): lower it to Low or find the evidence, never
relabel it a defect. A security question a reviewer left UNKNOWN-BLOCKED belongs in its report
as a High finding in the `security` dimension whose Fix is to answer it, since CLEAR is
impossible while it stands. Overlapping findings merge in the tool, and a two-level severity
gap is flagged for the user. When `review_add` answers that findings are `back to undecided`, show
the gate again and call `review_dispose` for them again before any remediation continues.

## 5. The finding gate

Always, when any finding exists. Show the user the `review_gate` answer: findings
by severity, security first, then by persona weight, with sources, location, any severity
conflict, and the decision so far. Then take the findings one at a time, in gate order. For each
`Fn`, call `review_dispose` with
`finding` and no `decisions`; the tool asks the user what to do with that finding and records the answer. Two of
the choices need a reason, which the tool asks with the choice. A severity conflict is settled
here by the decision the user makes about it:

```json
{"run_id": "20261005-103000", "by": "user", "finding": "F1"}
```

The answer says which findings are still undecided. An answer starting `needs input` means no one
could be asked through the tool: put the question it names to the user in one `AskUserQuestion`
dialog, then call again with `decisions` for that finding (several findings may go in one call):

```json
{"run_id": "20261005-103000", "by": "user", "decisions": {"F1": {"decision": "fix"}, "F2": {"decision": "accept-risk", "reason": "..."}}}
```

Nothing the user did not pick is remediated.

## 6. Comment the PR, always

Pass or fail, one finding or twenty: render the report and the abridged comment, check the
comment, and post it. `review_report` returns
text and writes no file, so the primary writes the full report (the call without `shape`) to
`RUNDIR/report.md` and this call's answer to `RUNDIR/pr-comment.md`:

```json
{"run_id": "20261005-103000", "shape": "comment"}
```

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/open-ticket/scripts/humanize_tracker_body.py" fix RUNDIR/pr-comment.md --shape comment
gh pr comment <PR> --body-file RUNDIR/pr-comment.md
```

Reword whatever `fix` still reports; the finding ids stay so the thread links back to the
report. Without `gh` or a PR, keep the file and surface the command. With nothing chosen for
fixing, the session ends here with the verdict `review_report` returned.

## 7. Remediate, risk first

Remediation needs a ticket, because its tasks live in the ticket. In
a codebase or branch run without one, offer open-ticket with the chosen findings as the
rollup, and stop.

Order: Critical findings and High security findings first, then the rest in gate order. For
each finding `Fn` chosen for fixing:

1. `task_start` with `slug`, `task_id` the next `R<n>` that `task_show` does not list, `by`
   `engineer`, `owned` the files the Fix touches and `acceptance` `AC-1`, the criterion the
   finding's Verify line proves. That number is the task's own and not the finding's: a sprint
   residual may hold `R1` already, so `F1` can be fixed under `R2`.
2. Dispatch an **engineer**: the residual variant for a single-concern merge-vader finding
   with usable Fix and Verify lines; the full template for uncle-bob findings, findings both
   personas raised, and anything Critical or High security. Either way the dispatch carries
   SLUG, that `R<n>` as the task id, and the persona's own id (`MV-n`, `UB-n`) in a slot of its
   own as the finding: a finding id is never the task id. A residual carries no contract id: the
   engineer runs the Verify command in sandboxed Bash and cites its output.
3. `task_verify` with `slug`, `task_id` that `R<n>`, the fix `commit`, and `assertions` mapping
   `AC-1` to the cited Verify output, then `review_resolve` with `run_id`, `finding` `Fn`,
   `result` `fixed` and `commit` (it takes only a finding the user chose to fix).
4. Failed or blocked: `task_mark` with `to` `failed` or `blocked` and a `reason` (a task the gate
   blocked already is `blocked`), then the owner's question unless `auto-escalate` is on,
   `task_start` on that `R<n>` with `by` `architect`, and **architect** once, then whats-broken,
   as in agents-assemble. Record `review_resolve` with `result` `failed` or `blocked` and a
   `reason` when a finding stops.

A finding whose reviewer wrote an Architect escalation line (a design decision beyond its
Fix) is a question for the user first. On their yes, dispatch architect in diagnose-replan
mode; its revised plan goes back to agents-assemble as new tasks, not into this loop.

Before every push: `contract_run` with `slug` and phase `landing`, and `task_ready`, as stick-the-landing does, then push (only the primary pushes) and dispatch gitty-up
with the PR number to watch CI.

## 8. Close

Re-render with `review_report` in both shapes, rewrite the two files, and replace the PR comment
(`gh pr comment <PR> --edit-last --body-file RUNDIR/pr-comment.md`) so it shows each finding's
outcome by id. The human review comes after this session; say so, and stop.
