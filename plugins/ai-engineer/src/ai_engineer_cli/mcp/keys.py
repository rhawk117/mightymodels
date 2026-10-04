# Sources are the Claude Code docs snapshot of 2026-10-03: mcp.md, plugins_components.md and
# mcp-quickstart.md, quoted as file:line below.

# mcp.md:83 and mcp.md:87 name the five `type` values a JSON entry may carry (`sdk` is skipped
# by Claude Code in a config file, so it is not listed); mcp.md:94 deprecates `sse`.
TRANSPORTS = frozenset({'stdio', 'http', 'sse', 'ws', 'streamable-http'})
REMOTE_TRANSPORTS = TRANSPORTS - {'stdio'}

# Keys on every server entry: `type` (mcp.md:83), `timeout` (mcp.md:417) and `alwaysLoad`
# (mcp.md:1519, "available on all server types").
SHARED_KEYS = frozenset({'type', 'timeout', 'alwaysLoad'})
# mcp.md:502 lists `command`, `args` and `env` for stdio servers.
STDIO_KEYS = SHARED_KEYS | {'command', 'args', 'env'}
# mcp.md:503 lists `url`, `headers` and `headersHelper` for http, sse and ws servers, and
# mcp.md:845 and mcp.md:863 show the `oauth` object on an http entry.
REMOTE_KEYS = SHARED_KEYS | {'url', 'headers', 'headersHelper', 'oauth'}
KEYS_BY_TRANSPORT = {
    **dict.fromkeys(['stdio'], STDIO_KEYS),
    **dict.fromkeys(REMOTE_TRANSPORTS, REMOTE_KEYS),
}

# mcp.md:501: the placeholders Claude Code substitutes; plugins_components.md:958 shows
# `${user_config.NAME}` in a plugin server's `env`.
PROVIDED_VARIABLES = frozenset({'CLAUDE_PLUGIN_ROOT', 'CLAUDE_PLUGIN_DATA', 'CLAUDE_PROJECT_DIR'})
USER_CONFIG_PREFIX = 'user_config.'

# mcp.md:672 to mcp.md:674 name these credential variables, which read as empty in a remote
# server's `url` and `headers`; the docs introduce the list with "such as", so it is not closed.
CREDENTIAL_VARIABLES = frozenset(
    {
        'ANTHROPIC_API_KEY',
        'ANTHROPIC_AUTH_TOKEN',
        'AWS_BEARER_TOKEN_BEDROCK',
        'HTTPS_PROXY',
        'NPM_TOKEN',
    }
)


def is_remote(server: dict[str, object]) -> bool:
    transport = server.get('type')
    return isinstance(transport, str) and transport in REMOTE_TRANSPORTS
