"""The workspace: state-directory paths, handoff files, containment and the exclude entry."""

from .errors import OutsideStateDirectoryError
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
    'HandoffFiles',
    'OutsideStateDirectoryError',
    'PersonaReport',
    'RecordFiles',
    'Workspace',
    'contained_in',
    'exclude_state',
    'find_root',
    'review_parts',
    'workspace_at',
    'workspace_of',
]
