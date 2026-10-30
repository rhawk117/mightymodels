# Workflow state tools

This page maps each call of the old `state` server to its tool on the new `workflow_state` server. The skills-and-agents port uses it to rewrite the old calls mechanically. Porting the skills and agents is not part of this change.

The old server key was `state`, so its tools were named `mcp__plugin_mightymodels_state__<tool>`. Each took one argument, `{"request": {"action": ..., ...}}`, and the action chose the operation. The new server key is `workflow_state` (`mcp-servers/workflow_state.json`), so by the same naming rule each tool is named `mcp__plugin_mightymodels_workflow_state__<tool>`. It takes its fields as flat arguments, with no `request` wrapper and no `action`.

## Tool map

One row per registered tool, 33 in all. The old action of `snapshot` is `none`, because that tool took no action. The input fields are the request schema's properties in schema order. The four hints are the tool's annotations. The test `tests/mcp/server/unit/test_mapping_doc.py` holds this table to the registered catalog.

| Old tool | Old action | New tool | Input fields | Title | Read-only | Destructive | Idempotent | Open world |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ticket` | `write` | `ticket_write` | `slug`, `summary`, `context`, `scope`, `compaction`, `branch`, `issue`, `jira`, `reference_urls`, `investigations` | Write a ticket | false | false | false | false |
| `ticket` | `validate` | `ticket_validate` | `slug` | Validate a ticket | false | false | false | false |
| `ticket` | `show` | `ticket_show` | `slug` | Show a ticket | true | false | true | false |
| `ticket` | `update-context` | `ticket_update_context` | `slug`, `context` | Update a ticket's context | false | false | false | false |
| `close` | `check` | `close_check` | `slug` | Check a ticket for live work | true | false | true | false |
| `close` | `close` | `close_ticket` | `slug`, `shipped`, `pr`, `gotchas` | Close a ticket | false | true | false | false |
| `task` | `start` | `task_start` | `slug`, `task_id`, `by`, `owned`, `acceptance`, `mode`, `too_large_approved_by` | Start a task | false | false | false | false |
| `task` | `verify` | `task_verify` | `slug`, `task_id`, `commit`, `assertions` | Verify a task | false | false | false | false |
| `task` | `mark` | `task_mark` | `slug`, `task_id`, `to`, `reason` | Mark a task | false | true | false | false |
| `task` | `show` | `task_show` | `slug` | Show the tasks | true | false | true | false |
| `task` | `ready` | `task_ready` | `slug` | Check the tasks are ready | true | false | true | false |
| `failed_fix` | `record` | `failed_fix_record` | `slug`, `task_id`, `hypothesis` | Record a failed fix | false | false | false | false |
| `contract` | `approve` | `contract_approve` | `slug`, `commands` | Approve the contract commands | false | false | false | false |
| `contract` | `status` | `contract_status` | `slug` | Show the contract status | true | false | true | false |
| `review` | `start` | `review_start` | `scope`, `depth`, `emphasis`, `slug`, `base`, `weights`, `persona` | Start a review | false | false | false | false |
| `review` | `override` | `review_override` | `run_id` | Override a review's models | false | false | false | false |
| `review` | `add` | `review_add` | `run_id`, `persona` | Add a reviewer's report | false | false | false | false |
| `review` | `gate` | `review_gate` | `run_id` | Gate a review | true | false | true | false |
| `review` | `report` | `review_report` | `run_id`, `shape` | Report a review | true | false | true | false |
| `review` | `list` | `review_list` | none | List the reviews | true | false | true | false |
| `review` | `dispose` | `review_dispose` | `run_id`, `decisions`, `by` | Decide a review's findings | false | false | false | false |
| `review` | `resolve` | `review_resolve` | `run_id`, `finding`, `result`, `commit`, `reason` | Resolve a review finding | false | false | false | false |
| `review` | `metrics` | `review_metrics` | `run_id`, `package_depth`, `max_listed` | Measure the code for a review | false | false | false | false |
| `signals` | `code-churn` | `signals_code_churn` | `target`, `since`, `baseline_ref`, `max_commits`, `all_history`, `limit` | Measure code churn | true | false | true | false |
| `signals` | `change-coupling` | `signals_change_coupling` | `target`, `since`, `baseline_ref`, `max_commits`, `all_history`, `limit`, `min_shared`, `max_changeset` | Measure change coupling | true | false | true | false |
| `signals` | `code-hotspots` | `signals_code_hotspots` | `target`, `since`, `baseline_ref`, `max_commits`, `all_history`, `limit` | Measure code hotspots | true | false | true | false |
| `snapshot` | `none` | `snapshot_take` | `slug`, `limit` | Take a snapshot | true | false | true | false |
| `investigation` | `start` | `investigation_start` | `target`, `kind` | Start an investigation | false | false | false | false |
| `investigation` | `add` | `investigation_add` | `investigation_id`, `round`, `entries` | Add to an investigation's ledger | false | false | false | false |
| `investigation` | `render` | `investigation_render` | `investigation_id` | Show an investigation's ledger | true | false | true | false |
| `investigation` | `knowns` | `investigation_knowns` | `investigation_id`, `kinds`, `limit` | Show the knowns table | true | false | true | false |
| `investigation` | `list` | `investigation_list` | none | List investigations | true | false | true | false |
| `crashout` | `add` | `crashout_add` | `ticket`, `branch`, `severity`, `verdict`, `rant`, `failures`, `root_cause`, `corrective_action`, `barked_back` | Journal a crashout | false | false | false | false |
| `crashout` | `stats` | `crashout_stats` | none | Show crashout patterns | true | false | true | false |
| `crashout` | `last` | `crashout_last` | none | Show the last crashout | true | false | true | false |
| `similarity` | `search` | `similarity_search` | `query`, `kind` | Search for similar rows | true | false | true | false |

Most new names are `<tool>_<action>`. Three differ: `close` with `close` is `close_ticket`, `ticket` with `update-context` is `ticket_update_context`, and `snapshot` is `snapshot_take`.

## Calls in the old skills and agents

The counts come from this command, run at the repository root:

```
rg --no-config -uu -o --no-filename 'mcp__plugin_mightymodels_state__\w+' .ref/mightymodels/skills .ref/mightymodels/agents | sort | uniq -c
```

Its scope is the skills and agents of the old plugin only, which hold 77 calls in 18 files. Over all of `.ref` the same pattern matches 80 times: these 77 and 3 in `tests/test_agent_frontmatter.py`. The `.ref` copy is untracked, so these counts are a record and no test reads them.

| Old tool | Calls |
| --- | --- |
| `task` | 14 |
| `ticket` | 14 |
| `investigation` | 13 |
| `contract` | 11 |
| `review` | 7 |
| `crashout` | 5 |
| `snapshot` | 5 |
| `failed_fix` | 4 |
| `close` | 2 |
| `similarity` | 2 |

The per-file table comes from the same pattern with `rg --no-config -uu -c` over the same two paths. The tools column gives each tool the file calls with its count.

| File | Calls | Tools called |
| --- | --- | --- |
| `agents/review/fact-checker.md` | 2 | `snapshot` 2 |
| `agents/workers/engineer.md` | 2 | `failed_fix` 2 |
| `skills/agent-debugging/SKILL.md` | 2 | `failed_fix` 2 |
| `skills/agents-assemble/SKILL.md` | 6 | `contract` 1, `task` 3, `ticket` 2 |
| `skills/ask-an-adult/SKILL.md` | 2 | `investigation` 2 |
| `skills/baton-pass/SKILL.md` | 7 | `investigation` 2, `snapshot` 3, `ticket` 2 |
| `skills/break-it-down/SKILL.md` | 6 | `contract` 2, `task` 4 |
| `skills/crashout/SKILL.md` | 5 | `crashout` 5 |
| `skills/game-plan/SKILL.md` | 4 | `contract` 2, `ticket` 2 |
| `skills/lets-investigate/SKILL.md` | 4 | `investigation` 4 |
| `skills/one-shot/SKILL.md` | 4 | `contract` 2, `ticket` 2 |
| `skills/open-ticket/SKILL.md` | 6 | `investigation` 2, `ticket` 4 |
| `skills/prune-ticket/SKILL.md` | 4 | `close` 2, `ticket` 2 |
| `skills/review-circus/SKILL.md` | 7 | `review` 6, `task` 1 |
| `skills/review-circus/references/review-state.md` | 1 | `review` 1 |
| `skills/stick-the-landing/SKILL.md` | 7 | `contract` 2, `task` 5 |
| `skills/what-we-know/SKILL.md` | 5 | `investigation` 3, `similarity` 2 |
| `skills/whats-broken/SKILL.md` | 3 | `contract` 2, `task` 1 |

## The AskUserQuestion recorder and the session pointer

The recorder, a PostToolUse hook on `AskUserQuestion`, is the only Decision record for
AskUserQuestion answers. The skills port must drop the skills' own gate-Decision writes, because
a skill that also writes one records the same answer twice.

The session pointer tells the recorder which ticket or investigation a session works on. A
PostToolUse hook sets it after each of the 20 slug-bearing workflow_state tools. A `slug` or
`ticket` in `tool_input` points the session at a ticket, and an `investigation_id` points it at
an investigation. The latest call wins. There is no ticket-directory gate: the pointer follows
the call, whether or not a ticket directory exists. The recorder writes nothing for a session
with no pointer.
