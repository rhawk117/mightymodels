# ticket.yml schema

The per-ticket source of truth, written once by open-ticket (`ticket_state.py write`) from the interview answers, then hand-tweaked by the user and checked by `ticket_state.py validate`. Every later session reads it before doing anything else; agent-file model pins are only the fallback for headless runs where nobody answered.

```yaml
task: "<slug>"                   # directory name under .mightymodels/
summary: "<one sentence>"
triaged-at: "<ISO datetime>"
context:                         # 1-6 lines: the knowns and decisions the next session
  - "<line>"                     # cannot afford to lose; no file:line
companion-docs:
  issue-number:                  # optional; GitHub issue number
  jira-key:                      # optional; Jira ticket key, e.g. "PROJ-123"
  reference-urls:                # external documentation used during triage only
    - "https://..."
subagent-models:
  primary-agent:                 # user hint, not source of truth
  code-scout: "gpt-5.6-luna"
  web-scout: "gpt-5.6-luna"
  qualitylens: "gpt-5.6-luna"
  engineer: "<derived>"          # see derivation rules
  architect: "<derived>"         # see derivation rules
  gitty-up: "gpt-5.6-luna"
  wingman: "gpt-5.6-sol"
  merge-vader-reviewer: "gpt-5.6-sol"
  uncle-bob-reviewer: "claude-sonnet-5"
handoff-context:
  scope: "<sm|med|large>"
  plan-first: <true|false>       # derived from the compaction answer
  branch-name: "<branch>"
  worktrees-okay: false          # dormant until engineers run in parallel
investigations:                  # lets-investigate ids whose ledgers this ticket came from
  - "<id>"
```

## The subset

`scripts/ticket_state.py` writes this file and reads back exactly this YAML subset, so hand edits validate as long as they stay inside it:

- mappings nested at most two levels, indented by two spaces;
- scalars: double-quoted strings (JSON escapes), plain words, integers, `true`/`false`, or empty for null;
- lists of scalars, one `- item` per line;
- `#` comments on their own line or after a value.

Anchors, flow collections (`[a, b]`, `{a: b}`), single quotes, and block scalars (`|`, `>`) are refused with the line number. Unknown keys are refused too, including retired worker keys such as `scout` or `budgetron`, because a key nobody reads is a setting that silently does nothing.

## Derivation rules

**engineer**: from the task-scope answer — `large` → `claude-sonnet-5`; `sm` or `med` → `gpt-5.6-luna`. The ticket value is the default for every task; the primary may bump a single gnarly task one tier at dispatch, but never above `claude-sonnet-5`, logging the reason in that task's ASKED stanza. A ticket has one scope value; its tasks do not.

**architect**: from the task-scope answer — `large` → `gpt-5.6-sol`; `sm` or `med` → `gpt-5.6-terra`. Architect recovers a failed engineer task, so its tier must sit above the engineer tier the scope derived; `claude-sonnet-5` is the engineer ceiling, which is why large scope skips terra.

**plan-first**: `true` when the user expects at least one compaction. `true` also means the baton-pass handoff prompt carries the switch-models reminder, and the next session's low-tier primary writes the plan before any dispatch.

**Reviewer split** (decision of record, 2026-08-29; carried to the reviewer workers 2026-09-28): `uncle-bob-reviewer` runs `claude-sonnet-5` and `merge-vader-reviewer` runs `gpt-5.6-sol`. The split is by role and report, not model — uncle-bob grades abstraction and structure, merge-vader runs the adversarial pre-merge pass, and their reports land separately so neither hedges the other. User-overridable per ticket like everything else in this block.

## Field discipline

No `review-weight` block — nothing consumes it (cut 2026-08-20). No key enters this schema without a named consumer in the flow; unused yaml is landfill with indentation. Consumers of record: `context` is read by every ramp before dispatch; `investigations` by what-we-know in sprint mode and by prune-ticket; `jira-key` is read by stick-the-landing (PR description link) and prune-ticket (archive header), alongside `issue-number`.
