"""ticket.yml as one frozen value, read only after the pre-scan accepts its text.

A refused file yields an error and no ticket, never a partly filled one. The values are decoded
as written: redaction, defaults and the checks between fields belong to the ticket service.
"""

import re
from typing import TYPE_CHECKING

import msgspec.yaml
from msgspec import DecodeError, Struct, ValidationError

from mightymodels_core.vocabulary.tickets import TicketScope

from .errors import TicketFileSyntaxError, TicketFileTypeError
from .ticket_scan import ROOT_PATH, is_skipped_line, scan_ticket, split_lines

if TYPE_CHECKING:
    from .errors import TicketFileIssue
    from .ticket_scan import TicketScan

type ModelNames = dict[str, str | None]

KEY_PATH_SUFFIX = re.compile(r' - at `(?P<path>[^`]+)`$')
MAPPING_VALUE = '[...]'
UNKNOWN_FIELD = re.compile(r'^Object contains unknown field `(?P<field>[^`]+)`')
SYNTAX_LINE = re.compile(r'line (?P<line>\d+)')


class HandoffContextFile(
    Struct, frozen=True, kw_only=True, gc=False, rename='kebab', forbid_unknown_fields=True
):
    branch_name: str | None = None
    scope: TicketScope | None = None
    plan_first: bool | None = None
    auto_escalate: bool | None = None
    worktrees_okay: bool | None = None


class CompanionDocsFile(
    Struct, frozen=True, kw_only=True, gc=False, rename='kebab', forbid_unknown_fields=True
):
    issue_number: int | None = None
    jira_key: str | None = None
    reference_urls: tuple[str, ...] | None = None


class TicketFile(Struct, frozen=True, kw_only=True, rename='kebab', forbid_unknown_fields=True):
    task: str | None = None
    summary: str | None = None
    triaged_at: str | None = None
    handoff_context: HandoffContextFile | None = None
    subagent_models: ModelNames | None = None
    companion_docs: CompanionDocsFile | None = None
    context: tuple[str, ...] | None = None
    investigations: tuple[str, ...] | None = None


def get_type_issue(error: ValidationError, scan: TicketScan) -> TicketFileTypeError:
    message = str(error)
    suffix = KEY_PATH_SUFFIX.search(message)
    key_path = suffix['path'] if suffix else ROOT_PATH
    reason = message.removesuffix(suffix[0]) if suffix else message
    if unknown := UNKNOWN_FIELD.match(message):
        key_path = f'{key_path}.{unknown["field"]}'
    return TicketFileTypeError(
        key_path=key_path, line=scan.line_of(key_path.removesuffix(MAPPING_VALUE)), reason=reason
    )


def get_syntax_issue(error: DecodeError) -> TicketFileSyntaxError:
    message = str(error)
    located = SYNTAX_LINE.search(message)
    line = int(located['line']) if located else None
    return TicketFileSyntaxError(line=line, reason=message.splitlines()[0])


def blank_skipped_lines(source: str) -> str:
    return '\n'.join('' if is_skipped_line(line) else line for line in split_lines(source))


def parse_ticket_file(source: str) -> TicketFile | TicketFileIssue:
    scan = scan_ticket(source)
    if isinstance(scan, TicketFileSyntaxError):
        return scan

    if scan.is_empty:
        return TicketFile()

    try:
        return msgspec.yaml.decode(blank_skipped_lines(source), type=TicketFile)
    except ValidationError as error:
        return get_type_issue(error, scan)
    except DecodeError as error:
        return get_syntax_issue(error)
