"""The scout-report spool: files a process outside the server leaves for it to take in.

The spool is the directory `SPOOL_DIRECTORY` in the plugin data directory, which every repository
shares. A report is one file in it named `<anything>.json`, whose content is a JSON object with
exactly these keys:

    {"repository_key": "owner/name", "scout": "code-scout", "target": "...", "report": "..."}

`scout` is `code-scout` or `web-scout`, `target` is at most `NAME_LIMIT` characters and `report`
is non-blank text of at most `PROSE_LIMIT`. A writer creates the file under a name that does not
end in `.json` and renames it to one that does, so the server never reads half a report.

The key is in the file, since the directory is shared. A server takes in the files of its own
repository and leaves every other file where it is. A file it cannot take in, because it is over
`SPOOL_FILE_BYTES`, is not a report, or holds text that redaction lengthens past its column, is
moved to `REJECTED_DIRECTORY` inside the spool under a name of its own and kept. Every path is the
data directory and a fixed name: the file says which repository it is for and nothing else, and no
key is ever part of a path.

A call takes in at most `SPOOL_FILES_PER_CALL` files, oldest name first.
"""

from itertools import islice
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from mightymodels_plugin.tools.similarity.schema import SpooledReport

SPOOL_DIRECTORY = 'scout-spool'
REJECTED_DIRECTORY = 'rejected'
REPORT_SUFFIX = '.json'
SPOOL_FILES_PER_CALL = 100
SPOOL_FILE_BYTES = 64 * 1024


def waiting_files(spool: Path) -> list[Path]:
    files = (
        file
        for file in sorted(spool.glob(f'*{REPORT_SUFFIX}'))
        if file.is_file(follow_symlinks=False)
    )
    return list(islice(files, SPOOL_FILES_PER_CALL))


def spooled_report(file: Path) -> SpooledReport | None:
    if file.stat().st_size > SPOOL_FILE_BYTES:
        return None
    try:
        return SpooledReport.model_validate_json(file.read_bytes())
    except ValidationError:
        return None


def set_aside(file: Path, spool: Path) -> None:
    rejected = spool.joinpath(REJECTED_DIRECTORY)
    rejected.mkdir(exist_ok=True)
    file.replace(rejected.joinpath(f'{uuid4().hex}-{file.name}'))
