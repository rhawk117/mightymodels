# Python MCP SDK facts the template depends on

Snapshot 2026-09-21 for the SDK; 2026-10-03 for the Claude Code statements. Tags: doc-verified (SDK docs source in github.com/modelcontextprotocol/python-sdk, main at 6affe5c, published at py.sdk.modelcontextprotocol.io), observed (run against `mcp==2.2.0` in this environment), inferred. `uv add mcp` resolves to the 2.x line today; the template targets 2.x and does not pin, per the plugin owner's choice.

## Version line

- `mcp` 2.2.0 is current (2.0.0 shipped in late July 2026, protocol revision late July 2026); the 1.x line continues as maintenance (1.30.0). Python floor `>=3.10`; the template requires `>=3.13` for `Self`, `TaskGroup` and one-argument `Generator`. doc-verified (PyPI)
- `mcp.server.fastmcp.FastMCP` no longer exists. Importing it raises `ModuleNotFoundError: ... FastMCP was renamed to MCPServer`. observed. Renames: `ctx.fastmcp` to `ctx.mcp_server`, `get_context()` removed, `FastMCPError` to `MCPServerError`, `McpError` to `MCPError`. doc-verified (whats-new)
- Migrating a 1.x server: change the import to `from mcp.server import MCPServer`, move `host`/`port`/`streamable_http_path` from the constructor to `run()`, replace `ctx.info()` with `logging`, replace `create_connected_server_and_client_session` with `Client(mcp)`, replace `streamablehttp_client` with `streamable_http_client`. doc-verified (migration)

## Server and tools, as the template uses them

```python
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

mcp = MCPServer('name', instructions='...', lifespan=lifespan)


@mcp.tool(
    name='count_files',
    description='...',
    annotations=ToolAnnotations(
        read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    ),
)
def count_files(params: Input, ctx: Context[AppState]) -> Output: ...
```

- A single Pydantic model parameter is supported and is nested, not flattened: the input schema is `{"properties": {"params": {"$ref": "#/$defs/Input"}}}` and the model must send `{"params": {...}}`. observed. Claude Code sends that schema as it is. It drops a tool whose top-level property names are not 1 to 64 characters of ASCII letters, digits, `_`, `.` and `-`, and it flattens a root-level `anyOf`, `oneOf` or `allOf` into one object, so keep the root an object. The `params` wrapper passes both checks. Claude Code docs, mcp page
- `Field(description=...)` on the model fields is what the model reads; descriptions are the tool's contract, so write them for the model, not for a human. doc-verified (servers/tools)
- The return annotation is the output schema; a `BaseModel` return fills both `content` (JSON text) and `structured_content`. observed. Whether Claude Code passes `structuredContent` through to the model is not documented (unverified); the `content` text carries the same JSON.
- `Context[AppState]` is a parameter the SDK injects and hides from the schema; the annotation must be evaluable at registration, so `server.py` does not use `from __future__ import annotations` (a deferred annotation cannot see a resolver defined inside `build_server`; the SDK raises `InvalidSignature`). observed
- `ctx.info/debug/warning/error` are deprecated as of 2026-07-28 (SEP-2577) and warn at call time; log with the `logging` module to stderr. doc-verified
- Annotation fields are snake_case in Python (`read_only_hint`), camelCase on the wire. doc-verified
- Only a `ToolError`'s message reaches the model; any other exception becomes "Error executing tool NAME". Raise `ToolError` with the text you want the model to act on. doc-verified (whats-new)
- Sync `def` tools run on a worker thread in v2; the lifespan runs once per server, including over HTTP. doc-verified

## Elicitation

- `await ctx.elicit(message, schema)` works only on legacy connections (2025-11-25 or earlier) and raises `NoBackChannelError` on a 2026-07-28 connection or with `json_response=True`. doc-verified
- Which revision a stdio server is asked for depends on the runtime: `MCP_SDK_GENERATION` (`v1` or `v2`) and `MCP_PROTOCOL_NEGOTIATION` (`auto` or `legacy`) set it, and from Claude Code v2.1.285 stdio servers are being asked for 2026-07-28 in sessions that fetch feature flags. `ctx.elicit` therefore raises on a connection that negotiated the new revision; the template uses resolvers so it works on both. Claude Code docs, mcp page
- The v2 form is a resolver: `Annotated[ElicitationResult[Confirm], Resolve(fn)]` on a tool parameter, where `fn` receives the tool's other arguments by name (and a `Context` if annotated) and returns either a value or `Elicit(message, Model)`. The framework performs the round trip; on 2026 connections it is a multi-round-trip `InputRequiredResult`. doc-verified, observed in-process
- Result handling: `match confirmation: case AcceptedElicitation(data=Confirm(proceed=True)): ...` (isinstance against the `ElicitationResult` union raises `TypeError`). doc-verified
- Schema constraint: flat primitive fields only (`str`, `int`, `float`, `bool`, `Literal[...]`); nested models raise `TypeError` at registration. doc-verified
- Test with `Client(mcp, elicitation_callback=accept)` where `async def accept(context: ClientRequestContext, params: ElicitRequestParams) -> ElicitResult`; the callback protocol names the parameters `context` and `params`, and ty checks that. observed
- Claude Code shows form and URL elicitation dialogs with no configuration, so the manual check is to call the confirming tool once in an interactive `claude` session and watch for the dialog. Whether the dialog drives the resolver's multi-round-trip on the installed version is unverified here. doc-verified (dialogs), unverified (round trip)

## Resources and prompts

- `@mcp.resource('scheme://{param}/path', name=..., description=..., mime_type=...)` with `def fn(param: str) -> str`; placeholders and parameters must match or registration raises `ValueError`. doc-verified
- `@mcp.prompt(name=..., description=...)` returning a `str` (one user message) or `list[Message]`. doc-verified
- Most servers need neither: a resource is for content the model should read without a tool call and a prompt is a canned conversation opener. The interview infers them from answers rather than asking head-on.

## Transports

- `mcp.run(transport='stdio')`; `mcp.run(transport='streamable-http', host='127.0.0.1', port=8000)` with `streamable_http_path='/mcp'` default. Options go to `run()`, never the constructor. doc-verified, observed
- SSE is superseded; the template does not offer it. doc-verified
- Streamable HTTP arms DNS-rebinding protection for localhost only; behind a real hostname pass `transport_security=`. doc-verified

## Client and tests

- `from mcp import Client`; `Client(mcp)` for in-process, `Client(StdioServerParameters(command='uv', args=[...], env={...}))` for a subprocess, `Client('http://host:port/mcp')` for HTTP; `async with` connects, then `list_tools()`, `call_tool(name, arguments)`, `list_prompts()`, `read_resource()`. observed
- The stdio child receives only an allow-list of environment variables; pass others through `env=`. doc-verified
- In-process tests negotiate 2026-07-28. observed

## Tooling

- `ty` 0.0.82, beta, `0.0.x` versioning. Strictness is `[tool.ty.rules] all = "error"` plus `[tool.ty.analysis] strict-equality-semantics = true` and `strict-generic-narrowing = true`; `[tool.ty.terminal] error-on-warning = true` removes a documented ambiguity about warnings and exit codes. doc-verified, observed (the template passes)
- Under `strict-equality-semantics`, a branch on a literal tuple constant is flagged as always true; the template types `TRANSPORTS: tuple[str, ...]` for that reason. observed
- ruff `select = ["ALL"]` with `D`, `CPY`, `COM812`, `ISC001` ignored, `flake8-quotes.inline-quotes = "single"` to match `format.quote-style = "single"`. observed clean on generated code after `ruff format`.
