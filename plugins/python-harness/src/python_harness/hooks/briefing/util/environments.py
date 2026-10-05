"""Interpreter facts from a virtualenv's pyvenv.cfg, and pin versus environment."""

import re
from collections.abc import Mapping
from types import MappingProxyType

from python_harness.hooks.briefing.domain import VirtualEnvironment

VERSION_KEYS = ('version_info', 'version')
IMPLEMENTATION_KEY = 'implementation'
MINOR_VERSION = re.compile(r'(\d+)\.(\d+)')


def parse_pyvenv_config(text: str) -> Mapping[str, str]:
    pairs = (line.partition('=') for line in text.splitlines())
    entries = {key.strip(): value.strip() for key, separator, value in pairs if separator}
    return MappingProxyType(entries)


def environment_from_config(path: str, config: Mapping[str, str]) -> VirtualEnvironment:
    versions = (config[key] for key in VERSION_KEYS if key in config)
    return VirtualEnvironment(
        path=path,
        version=next(versions, None),
        implementation=config.get(IMPLEMENTATION_KEY),
    )


def minor_version_of(text: str | None) -> tuple[int, int] | None:
    if text is None:
        return None
    found = MINOR_VERSION.search(text)
    if found is None:
        return None
    return int(found.group(1)), int(found.group(2))


def environment_differs_from_pin(pin: str | None, environment: str | None) -> bool:
    pinned = minor_version_of(pin)
    running = minor_version_of(environment)
    return pinned is not None and running is not None and pinned != running
