# Port smoke run

Run by hand on 2026-11-01 with Claude Code 2.1.316, on a scratch branch at commit `4252080`, against a throwaway ticket `port-smoke`, with the plugin loaded by `claude --plugin-dir .`. The output below is as the sessions printed it and the user pasted it.

## Long `contract_run` calls

Launched with `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT=60000` and the default 30-second heartbeat. An approved `sleep 150` completed through `contract_run`, and the primary waited for its result.

`contract_approve`, with `approved_by` left out:

```text
{"text":"contract: 1 commands (1 new)\n","passing":true,"commands":[],"retired":[]}
```

The call moved to the background after 114 seconds:

```text
MCP tool "plugin:mightymodels:mighty-mcp/contract_run" is still running after 114s. It was moved to the background as task kzevww291 and keeps running; you'll receive a notification with the result when it completes. You can keep working in the meantime. To stop it, use TaskStop with task_id "kzevww291". Note: it does not survive exiting this session.
```

Its final result:

```text
{"text":"L1 pass exit=0 150010ms (form)\n","passing":true,"receipts":[{"id":"L1","outcome":"pass","exit":0,"duration_ms":150010,"head":"4252080767c57dee0f5e90369cac69f942e507c0","stdout_tail":"","stderr_tail":"","approval_source":"form"}]}
```

### Control

Launched the same way, with `MIGHTYMODELS_CONTRACT_HEARTBEAT_SECONDS=90` as well. The call timed out, 92 seconds after the first `date` (17:33:50 to 17:35:22):

```text
MCP server "plugin:mightymodels:mighty-mcp" tool "contract_run" sent no response or progress for 85s; aborting. If this server is configured in your MCP settings, set a per-server "timeout" (ms) to allow longer silent runs for just this server; otherwise set CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT (ms) globally (0 disables).
```

### What this does and does not show

- The 30-second heartbeat kept the call alive past the idle limit, and a 90-second heartbeat let the limit end it.
- The limit fired at 85 seconds, not the 60 that was set. The CLI's timeout code gives 60 seconds for this setting, so the extra 25 seconds is unexplained. The 30-second heartbeat is inside either figure.
- The plan expected the control to take about 4 minutes. It took 92 seconds.
- The 30-minute default idle timeout rests on the CLI's code and was not run.
- Whether the server kept running the command after the control's abort, and whether it recorded a receipt, was not checked.
- The first run's two `date` calls are 148 seconds apart around a command that took 150 seconds, so those times are approximate. The receipt's `duration_ms` is the measured figure.

## Who can reach the contract tools

A `general-purpose` agent, which inherits its tools, called `contract_run`, `contract_approve` and `contract_retire` once each, in a separate short session. A PreToolUse hook refused all three. The agent's report of each outcome:

```text
PreToolUse:mcp__plugin_mightymodels_mighty-mcp__contract_run hook error: mightymodels: only the primary runs, approves and retires contract commands, so this `contract_run` call from a subagent was refused. Report back what you changed and verified, and the primary will act on the contract.
```

```text
PreToolUse:mcp__plugin_mightymodels_mighty-mcp__contract_approve hook error: mightymodels: only the primary runs, approves and retires contract commands, so this `contract_approve` call from a subagent was refused. Report back what you changed and verified, and the primary will act on the contract.
```

The third result reached this page garbled by the terminal paste, with the middle of the tool name and the backticked name in the message lost. What survived:

```text
PreToolUse:mcp__plugin_mightymodels_mightrror: mightymodels: only the primary runs,approves and retires contract commands, s from a subagent was refused. Report backwhat you changed and verified, and the primary will act on the contract.
```

The agent listed that result as item 3, `mcp__plugin_mightymodels_mighty-mcp__contract_retire`, with slug `port-smoke`, id `L1`, why `test`, approved_by `user`.

## Plugin loading

From the first smoke session, whose `contract_run` failed before it ran because the prompt had no `ticket_validate` step:

- A skill loads: `mightymodels:agents-assemble` loaded, first heading `# agents-assemble`.
- A `mighty-mcp` tool answers: `ticket_write` returned `wrote .mightymodels/port-smoke/ticket.yml; review it, then run validate`. `contract_run` was available.
- The old server is absent: no `mcp__plugin_mightymodels_state__` tools were available under `--plugin-dir`.
- A preloaded skill reaches its agent: `mightymodels:review:merge-vader` said its doctrine was already in context, first heading `# merge-vader persona doctrine`.
- Wingman reported "I can call exactly one tool: SubagentHandback." Asked in the short session to read `README.md`, it said it had no function to read a file, made no call, and knew nothing of the file. The session's agent list showed wingman with "All tools"; `agents/triage/wingman.md` declares `tools: []`. The agent's report agrees with that declaration and the listing does not. This rests on the agent's own report, so the conflict is recorded here and not proven either way.

## Other observations

- `contract_approve` answered `not approved: the user declined these commands` in the first session. The second session's approval went through the form (`approval_source` `form`). Whether the first answer was a person's choice is not recorded here.
- In all four sessions, auto mode's classifier gave no verdict on the Write of the results file, so the results reached this page by paste.
