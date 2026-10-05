"""Decoding and parsing config text into documents, or the reason it cannot be read."""

import configparser
from types import MappingProxyType

import tomllib

from python_harness.hooks.briefing.domain import (
    IniDocument,
    IniRead,
    IniSections,
    TextFile,
    TextRead,
    TomlDocument,
    TomlRead,
    UnreadableFile,
)


def decode_text(content: bytes, label: str) -> TextRead:
    try:
        return TextFile(content.decode('utf-8'))
    except UnicodeDecodeError as error:
        return UnreadableFile(label, f'is not UTF-8: {error.reason}')


def parse_toml(text: str, label: str) -> TomlRead:
    try:
        return TomlDocument(MappingProxyType(tomllib.loads(text)))
    except tomllib.TOMLDecodeError as error:
        reason = f'is not valid TOML: {error.msg} (line {error.lineno})'
        return UnreadableFile(label, reason)


def sections_of(parser: configparser.ConfigParser) -> IniSections:
    names = parser.sections()
    sections = {name: MappingProxyType(dict(parser[name])) for name in names}
    return MappingProxyType(sections)


def parse_ini(text: str, label: str) -> IniRead:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(text, source=label)
    except configparser.Error as error:
        reason = error.message.splitlines()[0]
        return UnreadableFile(label, f'is not valid INI: {reason}')
    return IniDocument(sections_of(parser))
