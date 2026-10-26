"""One log record per tool call, and the handlers that carry every record to stderr and a file.

A call record names the tool, the slug it addressed and how it ended, with its duration. It
never carries another argument value. The handlers go on the root logger, so the SDK's own
records reach them too; they have to be installed before the server is created, because the
SDK configures logging itself only when the root logger has no handler.
"""

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING, Literal, TextIO, TypeIs, get_args

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping
    from pathlib import Path

type LogLevel = Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
type CallOutcome = Literal['ok', 'refused', 'error']

CALL_LOGGER_NAME = 'mightymodels_mcp.calls'
LOG_LEVEL_VARIABLE = 'MIGHTYMODELS_LOG_LEVEL'
LEVEL_NAMES = get_args(LogLevel.__value__)
DEFAULT_LOG_LEVEL: LogLevel = 'INFO'
LOG_DIRECTORY = 'logs'
LOG_FILE_NAME = 'mightymodels-mcp.log'
LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s %(message)s'
CALL_MESSAGE = 'tool=%s slug=%s outcome=%s duration_ms=%.1f'

call_logger = logging.getLogger(CALL_LOGGER_NAME)


def is_log_level(value: object) -> TypeIs[LogLevel]:
    return value in LEVEL_NAMES


LOG_LEVELS = tuple(filter(is_log_level, LEVEL_NAMES))


class InvalidLogLevelError(Exception):
    def __init__(self, *, given: str) -> None:
        self.given = given
        accepted = ', '.join(LOG_LEVELS)
        super().__init__(f'{LOG_LEVEL_VARIABLE} is {given!r}; accepted levels are {accepted}')


def parse_log_level(environ: Mapping[str, str]) -> LogLevel | InvalidLogLevelError:
    given = environ.get(LOG_LEVEL_VARIABLE, DEFAULT_LOG_LEVEL)
    level = next((level for level in LOG_LEVELS if level == given.upper()), None)
    return InvalidLogLevelError(given=given) if level is None else level


@dataclass(slots=True, kw_only=True, frozen=True)
class CallRecord:
    tool_name: str
    slug: str | None
    outcome: CallOutcome
    duration_ms: float

    @property
    def level(self) -> int:
        return logging.ERROR if self.outcome == 'error' else logging.INFO

    def emit(self) -> None:
        call_logger.log(
            self.level,
            CALL_MESSAGE,
            self.tool_name,
            self.slug,
            self.outcome,
            self.duration_ms,
            extra={
                'tool_name': self.tool_name,
                'slug': self.slug,
                'outcome': self.outcome,
                'duration_ms': self.duration_ms,
            },
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class LogSettings:
    level: LogLevel
    data_directory: Path
    stream: TextIO
    max_bytes: int = 1_000_000
    backup_count: int = 3

    @property
    def directory(self) -> Path:
        return self.data_directory.joinpath(LOG_DIRECTORY)

    @property
    def file_path(self) -> Path:
        return self.directory.joinpath(LOG_FILE_NAME)


@contextmanager
def installed_logging(settings: LogSettings) -> Generator[None]:
    settings.directory.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        settings.file_path, maxBytes=settings.max_bytes, backupCount=settings.backup_count
    )
    handlers = (logging.StreamHandler(settings.stream), file_handler)
    formatter = logging.Formatter(LOG_FORMAT)
    root = logging.getLogger()
    previous_level = root.level
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)

    root.setLevel(settings.level)
    try:
        yield
    finally:
        root.setLevel(previous_level)
        for handler in handlers:
            root.removeHandler(handler)
            handler.close()
