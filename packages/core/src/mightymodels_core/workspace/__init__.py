"""The workspace: state-directory paths, handoff files, containment and the exclude entry."""

from .errors import (
    LoneSurrogateError,
    OutsideStateDirectoryError,
    TicketFileIssue,
    TicketFileSyntaxError,
    TicketFileTypeError,
)
from .exclude import EXCLUDE_LINE, exclude_state
from .handoffs import (
    HANDOFFS_DIRECTORY,
    LIVE_DEBUG_FILE,
    SNAPSHOT_NAME,
    HandoffFiles,
    RecordFiles,
)
from .paths import (
    PROJECT_DIR_VARIABLE,
    RUNTIME_DIRECTORY,
    STATE_DIRECTORY,
    TICKET_DRAFT,
    TICKET_FILE,
    contained_in,
    find_root,
    review_parts,
)
from .ticket_file import (
    CompanionDocsFile,
    HandoffContextFile,
    TicketFile,
    parse_ticket_file,
)
from .workspace import PersonaReport, Workspace, workspace_at, workspace_of

__all__ = [
    'EXCLUDE_LINE',
    'HANDOFFS_DIRECTORY',
    'LIVE_DEBUG_FILE',
    'PROJECT_DIR_VARIABLE',
    'RUNTIME_DIRECTORY',
    'SNAPSHOT_NAME',
    'STATE_DIRECTORY',
    'TICKET_DRAFT',
    'TICKET_FILE',
    'CompanionDocsFile',
    'HandoffContextFile',
    'HandoffFiles',
    'LoneSurrogateError',
    'OutsideStateDirectoryError',
    'PersonaReport',
    'RecordFiles',
    'TicketFile',
    'TicketFileIssue',
    'TicketFileSyntaxError',
    'TicketFileTypeError',
    'Workspace',
    'contained_in',
    'exclude_state',
    'find_root',
    'parse_ticket_file',
    'review_parts',
    'workspace_at',
    'workspace_of',
]
