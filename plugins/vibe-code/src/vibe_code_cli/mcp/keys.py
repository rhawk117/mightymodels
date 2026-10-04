from dataclasses import dataclass, field
from enum import StrEnum


class Transport(StrEnum):
    STDIO = 'stdio'
    HTTP = 'http'
    SSE = 'sse'
    WS = 'ws'
    STREAMABLE_HTTP = 'streamable-http'


REMOTE_TRANSPORTS = (Transport.HTTP, Transport.SSE, Transport.WS, Transport.STREAMABLE_HTTP)


def keys_by_transport() -> dict[str, tuple[str, ...]]:
    shared = ('type', 'timeout', 'alwaysLoad')
    remote = (*shared, 'url', 'headers', 'headersHelper', 'oauth')
    return {
        Transport.STDIO: (*shared, 'command', 'args', 'env'),
        **dict.fromkeys(REMOTE_TRANSPORTS, remote),
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class TransportKeys:
    by_transport: dict[str, tuple[str, ...]] = field(default_factory=keys_by_transport)


PROVIDED_VARIABLES = ('CLAUDE_PLUGIN_ROOT', 'CLAUDE_PLUGIN_DATA', 'CLAUDE_PROJECT_DIR')
USER_CONFIG_PREFIX = 'user_config.'
CREDENTIAL_VARIABLES = (
    'ANTHROPIC_API_KEY',
    'ANTHROPIC_AUTH_TOKEN',
    'AWS_BEARER_TOKEN_BEDROCK',
    'HTTPS_PROXY',
    'NPM_TOKEN',
)
