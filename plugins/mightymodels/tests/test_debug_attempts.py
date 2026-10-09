"""A stuck engineer's failed fixes: recorded per task, three accepted, the fourth refused."""

from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from mightymodels_plugin.declarative import PROSE_LIMIT
from mightymodels_plugin.redaction import RedactedTextTooLongError
from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.task.errors import FixesSpentError, FixNotUnderwayError
from mightymodels_plugin.tools.task.repository import FAILED_FIX_LIMIT, task_transaction
from mightymodels_plugin.tools.task.schema import Implementer, Status, TaskFailedFix, TaskStart
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.tests.support import (
    StateServer,
    text_of,
    workspace_database,
)
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService
from mightymodels_plugin.workspace import workspace_at

type GitRunner = Callable[..., str]

TICKET = Slug('retry-queue')
OTHER_TICKET = Slug('drain-loop')
HYPOTHESES = ('the sleep is in the drain loop', 'the batch size is zero', 'the lock is held')
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'branch': 'fix/retry-queue',
        'context': ['drain loop sleeps between batches'],
    }
)
START = TaskStart(by=Implementer.ENGINEER, owned=('src/queue.py',))
CREDENTIALS = '://user:hunter2@'
REDACTED_CREDENTIALS = '://[REDACTED:url-credentials]@'


def fix_of(hypothesis: str) -> TaskFailedFix:
    return TaskFailedFix(hypothesis=hypothesis)


def tried(tasks: TaskService, slug: Slug, task_id: str) -> list[str]:
    with task_transaction(tasks.database) as repository:
        return repository.failed_fixes(slug, task_id)


def stage_and_start(tickets: TicketService, tasks: TaskService, slug: Slug, *task_ids: str) -> None:
    tickets.write(slug, ANSWERS)
    tickets.validate(slug)
    for task_id in task_ids:
        tasks.start(slug, task_id, START)


@dataclass(slots=True, kw_only=True, frozen=True)
class AnotherRepository:
    tasks: TaskService
    tickets: TicketService


@pytest.fixture
def started(ticket_service: TicketService, task_service: TaskService) -> TaskService:
    stage_and_start(ticket_service, task_service, TICKET, 'T1', 'T2')
    stage_and_start(ticket_service, task_service, OTHER_TICKET, 'T1')
    return task_service


@pytest.fixture
def three_failed(started: TaskService) -> TaskService:
    for hypothesis in HYPOTHESES:
        started.record_failed_fix(TICKET, 'T1', fix_of(hypothesis))
    return started


@pytest.fixture
def another_repository(
    tmp_path: Path, data_directory: Path, git: GitRunner
) -> Generator[AnotherRepository]:
    root = tmp_path.joinpath('another')
    root.mkdir()
    git(root, 'init', '--quiet')
    workspace = workspace_at(root)
    workspace.exclude_state_from_git()
    with workspace_database(workspace, data_directory) as database:
        yield AnotherRepository(
            tasks=TaskService(workspace=workspace, database=database),
            tickets=TicketService(workspace=workspace, database=database),
        )


class TestAFailedFix:
    def test_is_recorded_with_the_hypothesis_it_tested(self, started: TaskService) -> None:
        view = started.record_failed_fix(TICKET, 'T1', fix_of(HYPOTHESES[0]))

        assert tried(started, TICKET, 'T1') == [HYPOTHESES[0]]
        assert HYPOTHESES[0] in view.text
        assert [record.status for record in view.tasks] == [Status.IN_PROGRESS]

    def test_says_how_many_fixes_are_left(self, started: TaskService) -> None:
        started.record_failed_fix(TICKET, 'T1', fix_of(HYPOTHESES[0]))
        view = started.record_failed_fix(TICKET, 'T1', fix_of(HYPOTHESES[1]))

        assert view.text.splitlines()[0].startswith('T1 failed fix 2 recorded')
        assert view.text.splitlines()[1] == '1 left'

    def test_is_refused_on_a_task_that_is_not_in_progress(self, started: TaskService) -> None:
        with pytest.raises(FixNotUnderwayError) as refused:
            started.record_failed_fix(TICKET, 'T9', fix_of(HYPOTHESES[0]))

        assert (refused.value.task_id, refused.value.current) == ('T9', Status.PENDING)
        assert tried(started, TICKET, 'T9') == []


class TestThreeFailedFixesOfOneTask:
    def test_are_all_accepted_in_order(self, three_failed: TaskService) -> None:
        assert len(HYPOTHESES) == FAILED_FIX_LIMIT
        assert tried(three_failed, TICKET, 'T1') == list(HYPOTHESES)


class TestAFourthFailedFix:
    @pytest.fixture
    def refusal(self, three_failed: TaskService) -> FixesSpentError:
        with pytest.raises(FixesSpentError) as refused:
            three_failed.record_failed_fix(TICKET, 'T1', fix_of('a fourth idea'))
        return refused.value

    def test_is_refused_with_the_three_hypotheses_in_order(self, refusal: FixesSpentError) -> None:
        assert refusal.tried == HYPOTHESES
        assert str(refusal).startswith('T1 is blocked')
        positions = [str(refusal).index(hypothesis) for hypothesis in HYPOTHESES]
        assert positions == sorted(positions)

    def test_stores_nothing(self, three_failed: TaskService, refusal: FixesSpentError) -> None:
        assert refusal.task_id == 'T1'
        assert tried(three_failed, TICKET, 'T1') == list(HYPOTHESES)

    def test_is_answered_by_the_tool_as_an_error_and_not_a_traceback(
        self, three_failed: TaskService, connected_server: StateServer
    ) -> None:
        arguments: dict[str, object] = {
            'action': 'record-failed-fix',
            'slug': TICKET.root,
            'payload': {'task_id': 'T1', 'change': {'hypothesis': 'a fourth idea'}},
        }

        (result,) = connected_server.call(('task', arguments))

        text = text_of(result)
        assert result.is_error
        assert 'T1 is blocked' in text
        assert [text.index(hypothesis) for hypothesis in HYPOTHESES] == sorted(
            text.index(hypothesis) for hypothesis in HYPOTHESES
        )
        assert 'Traceback' not in text
        assert tried(three_failed, TICKET, 'T1') == list(HYPOTHESES)


class TestTheCount:
    def test_of_another_task_starts_at_zero(self, three_failed: TaskService) -> None:
        three_failed.record_failed_fix(TICKET, 'T2', fix_of('another task, first idea'))

        assert tried(three_failed, TICKET, 'T2') == ['another task, first idea']

    def test_of_another_ticket_starts_at_zero(self, three_failed: TaskService) -> None:
        three_failed.record_failed_fix(OTHER_TICKET, 'T1', fix_of('another ticket, first idea'))

        assert tried(three_failed, OTHER_TICKET, 'T1') == ['another ticket, first idea']
        assert tried(three_failed, TICKET, 'T1') == list(HYPOTHESES)

    def test_of_another_repository_key_starts_at_zero(
        self, three_failed: TaskService, another_repository: AnotherRepository
    ) -> None:
        stage_and_start(another_repository.tickets, another_repository.tasks, TICKET, 'T1')

        another_repository.tasks.record_failed_fix(TICKET, 'T1', fix_of('other key, first idea'))

        assert tried(another_repository.tasks, TICKET, 'T1') == ['other key, first idea']
        assert tried(three_failed, TICKET, 'T1') == list(HYPOTHESES)


class TestTheHypothesis:
    def test_is_redacted_before_it_is_stored(self, started: TaskService) -> None:
        started.record_failed_fix(TICKET, 'T1', fix_of(f'the config holds {CREDENTIALS}'))

        (stored,) = tried(started, TICKET, 'T1')
        assert REDACTED_CREDENTIALS in stored
        assert 'hunter2' not in stored

    def test_is_refused_when_redaction_lengthens_it_past_its_column(
        self, started: TaskService
    ) -> None:
        hypothesis = 'x' * (PROSE_LIMIT - len(CREDENTIALS)) + CREDENTIALS

        with pytest.raises(RedactedTextTooLongError) as refused:
            started.record_failed_fix(TICKET, 'T1', fix_of(hypothesis))

        assert refused.value.field == 'hypothesis'
        assert tried(started, TICKET, 'T1') == []
