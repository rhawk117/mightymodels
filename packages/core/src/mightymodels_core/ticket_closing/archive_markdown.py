"""The Markdown of an archive: what a closed ticket shipped, in a fixed and bounded set of lines.

Each part of the record is one line, the decisions and the gotchas are bulleted under their own
line and capped, and the last line names the JSON record beside the archive. The decisions are the
linked ledgers' first and the review's reasons after, as many as the cap leaves room for. The
renderer is pure: the caller picks the record's file name and writes both archive files.
"""

from itertools import islice
from typing import TYPE_CHECKING

from mightymodels_core.primitives import short_head
from mightymodels_core.primitives.value_types import ARCHIVES_DIRECTORY

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from mightymodels_core.primitives import TaskId
    from mightymodels_core.ticket_closing.archive import (
        ArchivedCommand,
        ArchivedReview,
        ArchivedTask,
        ArchiveRecord,
    )
    from mightymodels_core.tickets.records import Tracker
    from mightymodels_core.vocabulary.tasks import Worker

NONE_RECORDED = 'none recorded'


def bullet_lines(items: Iterable[str]) -> list[str]:
    lines = [f'- {item}' for item in items]
    return lines or [f'- {NONE_RECORDED}']


def tracker_text(tracker: Tracker) -> str:
    issue = '' if tracker.issue is None else f'#{tracker.issue}'
    jira = tracker.jira or ''
    return ' '.join(part for part in (issue, jira) if part) or 'none'


def shipped_line(record: ArchiveRecord) -> str:
    closing = record.closing
    pull_request = 'none' if closing.pr is None else closing.pr
    parts = (
        f'shipped: {closing.shipped}',
        f'PR: {pull_request}',
        f'tracker: {tracker_text(record.tracker)}',
        f'pruned: {closing.closed_at.date().isoformat()}',
        f'head: {short_head(closing.head)}',
    )
    return ' · '.join(parts)


def attempts_text(attempts: Mapping[Worker, int]) -> str:
    return ', '.join(f'{worker} {count}' for worker, count in attempts.items())


def tasks_line(tasks: Mapping[TaskId, ArchivedTask]) -> str:
    shown = '; '.join(
        f'{task_id} ({attempts_text(task.attempts)})' for task_id, task in tasks.items()
    )
    return f'tasks: {shown or NONE_RECORDED}'


def checks_line(verification: Sequence[ArchivedCommand]) -> str:
    not_passing = [command.key for command in verification if command.outcome != 'pass']
    passing = len(verification) - len(not_passing)
    tail = f'; not passing: {", ".join(not_passing)}' if not_passing else ''
    return f'checks: {len(verification)} contract commands, {passing} passing at last run{tail}'


def review_line(review: ArchivedReview | None) -> str:
    if review is None:
        return 'review: none'

    decided = '; '.join(
        f'{decision} {", ".join(finding_keys)}'
        for decision, finding_keys in review.by_decision.items()
    )
    run = f'run {review.run} ({review.depth})'
    return f'review: {run}, {review.findings} findings; {decided or "no decisions"}'


def decision_lines(record: ArchiveRecord, decision_limit: int) -> list[str]:
    decided = [f'{decision.text} ({decision.origin})' for decision in record.decisions]
    reasons = {} if record.review is None else record.review.reasons
    reviewed = (f'review {key}: {reason}' for key, reason in reasons.items())
    accepted = islice(reviewed, max(decision_limit - len(decided), 0))
    return bullet_lines([*decided, *accepted])


def archive_markdown(record: ArchiveRecord, record_name: str, decision_limit: int) -> str:
    lines = [
        f'# {record.slug}',
        shipped_line(record),
        tasks_line(record.tasks),
        checks_line(record.verification),
        review_line(record.review),
        'decisions:',
        *decision_lines(record, decision_limit),
        'gotchas:',
        *bullet_lines(record.closing.gotchas),
        f'details: {ARCHIVES_DIRECTORY}/{record_name}',
    ]
    return '\n'.join(lines) + '\n'
