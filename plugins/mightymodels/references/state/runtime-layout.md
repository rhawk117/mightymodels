# Runtime layout for hooks

Read before changing a hook, a receipt struct, or any skill script whose files a hook reads. The hooks in `src/mightymodels_plugin/hooks.py` adapt the skill scripts' file contracts; they never define a second state model.

## Where the state database is

The state database is `mightymodels.db` in the plugin data directory, the directory Claude Code names in `CLAUDE_PLUGIN_DATA` for the state server and for hook commands. It is outside every repository and serves all of them: each row carries a repository key, the origin remote's `owner/name` or, with no origin, a hash of the toplevel path. A command run through the Bash tool gets none of the plugin's variables, so the SessionStart hook, `mightymodels session-start`, appends one line to the session's env file (`CLAUDE_ENV_FILE`) that exports the same directory as `MIGHTYMODELS_DATA_DIR`, and `mightymodels verify run` reads that to open the file the server opened. Without the variable, or outside a git work tree, the server answers every tool call with what is missing and `verify run` exits 2 with the same on standard error.

This breaks with earlier versions, which kept the database inside the repository under `.mightymodels/`. That file is not read, imported or changed, so state recorded in it does not carry over, and it can be deleted. The new file carries a schema version stamp, and a file with another stamp is refused by name instead of read.

## What hooks read

| File                                   | Owner                                                          | Read by                                                               |
| -------------------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------- |
| `.mightymodels/SLUG/work-unit.json`    | open-ticket's ticket_state.py, agents-assemble's task_state.py | every hook, to find the ticket whose `ticket.branch` is checked out   |
| `.mightymodels/SLUG/transitions.jsonl` | task_state.py                                                  | completion-gate, to find who started an in-progress task              |
| `.mightymodels/SLUG/briefs/task-NN.md` | agents-assemble and the engineer                               | completion-gate, for the DONE half and its commit                     |
| the git repository                     | git, read through pygit2                                       | every hook, for branch, HEAD, status, ignore rules, and commit ranges |

## What hooks write

| File                                              | Writer                                                                                                            |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `.mightymodels/.runtime/decisions/receipts.jsonl` | decision-recorder                                                                                                 |
| `.mightymodels/.runtime/subagents/receipts.jsonl` | subagent-recorder                                                                                                 |
| `.mightymodels/.runtime/gate/SHA256`              | completion-gate, an empty marker named by the SHA-256 of session, worker, and tasks that makes its block one-shot |
| `.mightymodels/SLUG/handoffs/snapshot.{json,md}`  | baton-pass's snapshot.py, run by workflow-state-snapshot                                                          |

Receipt shapes are [`receipt.schema.json`](./receipt.schema.json). Hooks never create `.mightymodels/` and never edit git's exclude file: the skill scripts that create the directory add `.mightymodels/` to `info/exclude`, and a hook refuses to write unless git reports the directory ignored.

Each receipt writer holds an exclusive `receipts.jsonl.lock` sidecar lock until its append
is flushed and closed. The standalone prune script uses the same lock around reading and
atomically replacing the receipt stream. Lock files remain in place; deleting one could
let writers lock different inodes. The protocol uses `flock` on POSIX and byte locking on
Windows. Both implementations must stay in sync and require no additional dependency.

## The branch ticket

A hook's ticket is the one whose `work-unit.json` names the checked-out branch and is not `closed`. A detached HEAD, no match, or two matches mean no ticket: receipts are written with `ticket: null`, and the gate and the snapshot do nothing. Outside a git repository every hook except session-bootstrap does nothing.

## Launch

Each hooks.json entry sets `cwd` to `${PLUGIN_ROOT}`, `UV_CACHE_DIR=${PLUGIN_DATA}/uv-cache`, `PYTHONSAFEPATH=1`, and `PYTHONUNBUFFERED=1`, then runs `uv run --frozen --no-dev --quiet mightymodels_plugin HOOK_NAME --plugin-root "${PLUGIN_ROOT}"`. uv discovers and creates or reuses the project environment from the hook cwd; the safe Python path keeps repository packages from shadowing the plugin's code, and `tests/test_launch.py` proves this with decoys. `--plugin-root` lets the snapshot hook reach `skills/baton-pass/scripts/snapshot.py`. A warm launch costs about 0.2 seconds, most of it importing pygit2.
