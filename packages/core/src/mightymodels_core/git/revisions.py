"""The revision names git is allowed to be asked about.

A name is plain when the whole of it matches `SAFE_REVISION`. The first character class keeps
a leading dash out, so a name can never reach git as an option, and `fullmatch` keeps a
trailing newline out, which `$` would accept.
"""

import re

from .errors import UnsafeRevisionError

SAFE_REVISION = re.compile(r'[0-9A-Za-z][0-9A-Za-z._/-]*')


def revision_error(*revisions: str) -> UnsafeRevisionError | None:
    unsafe = next(
        (revision for revision in revisions if not SAFE_REVISION.fullmatch(revision)), None
    )
    return None if unsafe is None else UnsafeRevisionError(revision=unsafe)
