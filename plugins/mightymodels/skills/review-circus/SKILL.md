---
name: review-circus
description: >-
  Review a diff, branch, ticket, or whole codebase with the mightymodels persona reviewers. One
  ask-user gate sets depth (quick Luna, standard Terra, deep on ticket.yml's reviewer models),
  persona emphasis, and scope; review_state.py records the run, metrics.py and review_signals.py
  measure, merge-vader-reviewer and uncle-bob-reviewer report, and their findings are normalized,
  deduplicated, and presented by id through ask-user. Only the findings the user picks go to
  remediation, risk first, through task_state.py; an abridged PR comment is always posted. Use for
  "run the review circus", "review the sprint", "full review pass", "both reviewers on this", and
  for a quick single-persona pass: "quick merge-vader on this branch", "uncle-bob this module",
  "is this safe to merge". Not for fixing CI (stick-the-landing) or mid-sprint work
  (agents-assemble).
---

# review-circus

Two reviewers with different worldviews, and this session's primary as the ringmaster: it
sets the profile, measures, dispatches, normalizes, and routes what the user chooses to fix.
It never reviews code itself and never invents a finding. An empty run means the reviewers
have not reported, not that the primary should improvise.

Run the scripts from the repository root, where `BASE` is the `Base directory for this skill`
line. Subagents do not inherit it, so every path a dispatch carries is absolute.

- `python3 BASE/scripts/review_state.py` records the run, the findings, and the decisions.
- `python3 BASE/scripts/metrics.py` measures structure (fan-in, fan-out, cycles, sizes).
- `python3 BASE/scripts/review_signals.py` measures git history (churn, coupling, hotspots).

Read `references/profiles.md` and `references/review-state.md` before the first run in a
session, and `agents-assemble/references/contracts.md` for the severity table. Dispatch every
worker through prompting-subagents.

## 1. Profile

One ask-user dialog, with only what the conversation has not already settled:

- **Scope**: diff, branch (against which base), ticket, or codebase.
- **Depth**: quick, standard, or deep. Say what each costs (profiles.md): quick is one
  persona on Luna, standard is Terra, deep runs ticket.yml's reviewer models.
- **Emphasis**: release-readiness, maintainability, balanced, or custom weights.
- For a quick review with balanced weights: which persona.

Then record it:

```bash
python3 BASE/scripts/review_state.py start --scope ticket --slug SLUG --base main --depth standard --emphasis balanced
```

It prints the run id, the run directory, and each persona's model. Every later step names
the run with `--run RUN`.

## 2. Measure

When uncle-bob-reviewer is in the run, measure structure into the run directory:

```bash
python3 BASE/scripts/metrics.py <repo root> --out RUNDIR/uncle-bob-metrics.json
```

Add `--package-depth 2` when the repository is one top-level package. When the languages are
ones it does not parse (it reads Python, JavaScript, and TypeScript), skip it and say so in
the dispatch.

At standard and deep, pick the history window for review_signals.py per profiles.md
(`--baseline-ref BASE` for branch and ticket scope). At standard and deep, a code-scout
surface triage also runs first: diff stat, risk hotspots (auth, input handling, CI config,
dependency manifests), tests covering the changed area. Quick skips both unless the persona
names a specific gap.

## 3. Dispatch the personas

Dispatch each persona in the run, in parallel, with prompting-subagents' reviewer template
and the model the run recorded. The packet carries the doctrine
(`BASE/references/personas/merge-vader.md` or `uncle-bob.md`), `BASE/references/profiles.md`,
`BASE/references/idiom-evidence.md`, the run directory, the depth and the persona's role (the
heavier weight leads), the metrics path, the signals script path and window, and for a
ticket, ticket.yml, the issue, and the plan (merge-vader's conformance check needs them).

Personas gather their own evidence through code-scout, web-scout, and qualitylens, and
nothing else. Write each response unchanged to `RUNDIR/MERGE-VADER-REPORT.md` or
`RUNDIR/UNCLE-BOB-REPORT.md`. Wait for every persona in the run.

## 4. Normalize

Turn every finding in the reports into one JSON array and record it:

```bash
python3 BASE/scripts/review_state.py add --run RUN <<'JSON'
[{"sources": ["MV-3"], "severity": "High", "security": true, "kind": "defect", "title": "...",
  "location": "path:line", "fix": "...", "verify": "..."}]
JSON
```

Copy severities, locations, Fix and Verify lines as the reviewer wrote them. Mark structure
and idiom findings `quality` and carry their evidence cite; the script refuses a quality
finding at Medium or above without one (idiom-evidence.md), and the answer is to lower it to
Low or to find the evidence, never to relabel it a defect. A security question a reviewer
left UNKNOWN-BLOCKED becomes a High security finding whose Fix is to answer it, since CLEAR is
impossible while it stands. Overlapping findings merge in the script, and a two-level severity
gap is flagged for the user.

## 5. The finding gate

Always, when any finding exists. Show the user `review_state.py gate --run RUN`: findings by
severity, security first, then by persona weight, with sources, location, and any severity
conflict. One ask-user dialog: which findings to fix now. For the rest, defer (ticketed for
later), accept the risk, or dismiss; the last two need a reason. A severity conflict is
settled here by the decision the user makes about it. Record the answer:

```bash
python3 BASE/scripts/review_state.py dispose --run RUN <<'JSON'
{"by": "user", "decisions": {"F1": {"decision": "fix"}, "F2": {"decision": "accept-risk", "reason": "..."}}}
JSON
```

Nothing the user did not pick is remediated.

## 6. Comment the PR, always

Pass or fail, one finding or twenty: render the report and the abridged comment, check the
comment, and post it.

```bash
python3 BASE/scripts/review_state.py report --run RUN
python3 BASE/scripts/review_state.py report --run RUN --shape comment
python3 BASE/../open-ticket/scripts/humanize_tracker_body.py fix RUNDIR/pr-comment.md --shape comment
gh pr comment <PR> --body-file RUNDIR/pr-comment.md
```

Reword whatever `fix` still reports; the finding ids stay so the thread links back to the
report. Without `gh` or a PR, keep the file and surface the command. With nothing chosen for
fixing, the session ends here with the verdict the script computed.

## 7. Remediate, risk first

Remediation needs a ticket, because its proof lives in the ticket's verification contract. In
a codebase or branch run without one, offer open-ticket with the chosen findings as the
rollup, and stop.

Order: Critical findings and High security findings first, then the rest in gate order. For
each finding `Fn` chosen for fixing:

1. `task_state.py start --slug SLUG --task Rn --by engineer --owned <files the Fix touches>`
   (agents-assemble's script, `BASE/../agents-assemble/scripts/`).
2. The finding's Verify command goes to the user as contract id `Rn.AC-1` in one ask-user
   dialog, then `verification.py contract` (game-plan's script).
3. Dispatch an **engineer**: the residual variant for a single-concern merge-vader finding
   with usable Fix and Verify lines; the full template for uncle-bob findings, findings both
   personas raised, and anything Critical or High security.
4. `verification.py run --id Rn.AC-1 --phase review`, then `task_state.py verify --task Rn --commit <commit>`, then `review_state.py resolve --run RUN --finding Fn --result fixed --commit <commit>`.
5. Failed or blocked: `task_state.py mark`, then **architect** once, then whats-broken, as in
   agents-assemble. Record `resolve --result failed|blocked --reason ...` when a finding stops.

A finding whose reviewer wrote an Architect escalation line (a design decision beyond its
Fix) is a question for the user first. On their yes, dispatch architect in diagnose-replan
mode; its revised plan goes back to agents-assemble as new tasks, not into this loop.

Before every push: `verification.py run --all --phase review` and `task_state.py ready`, as
stick-the-landing does, then push and have gitty-up watch CI.

## 8. Close

Re-render with `report` and `report --shape comment`, and replace the PR comment
(`gh pr comment <PR> --edit-last --body-file RUNDIR/pr-comment.md`) so it shows each finding's
outcome by id. The human review comes after this session; say so, and stop.
