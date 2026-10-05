"""The `review` tool through the SDK's in-memory client."""

import asyncio
from pathlib import Path

import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent
from mightymodels_plugin.server import build_server

FIXTURE = Path(__file__).parent.joinpath('fixtures', 'merge-vader-report.md')
START = {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'}
DECISIONS = {
    'by': 'user',
    'decisions': {
        'F1': {'decision': 'fix'},
        'F2': {'decision': 'accept-risk', 'reason': 'the endpoint is internal'},
    },
}
FORBIDDEN = ('report.md', 'pr-comment.md', 'review-run.json', 'findings.jsonl')


def text_of(result: CallToolResult) -> str:
    return ''.join(block.text for block in result.content if isinstance(block, TextContent))


async def call(*calls: tuple[dict[str, object], Path | None]) -> list[CallToolResult]:
    async with Client(build_server()) as client:
        results = []
        for arguments, report in calls:
            if report is not None:
                report.write_text(FIXTURE.read_text(encoding='utf-8'), encoding='utf-8')
            results.append(await client.call_tool('review', arguments))
        return results


@pytest.fixture
def project(repository: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(repository))
    return repository


def start(project: Path) -> tuple[str, Path]:
    (started,) = asyncio.run(call(({'action': 'start', 'payload': START}, None)))
    run = started.structured_content['run_id']
    return run, project.joinpath('.mightymodels', '.runtime', 'reviews', run)


@pytest.mark.usefixtures('project')
class TestReviewCalls:
    def test_a_run_is_recorded_ingested_decided_resolved_and_reported_without_a_file(
        self, project: Path
    ) -> None:
        run, directory = start(project)
        report = directory.joinpath('MERGE-VADER-REPORT.md')

        added, gate, disposed, resolved, full, comment, listed = asyncio.run(
            call(
                ({'action': 'add', 'run_id': run, 'payload': {'persona': 'merge-vader'}}, report),
                ({'action': 'gate', 'run_id': run}, None),
                ({'action': 'dispose', 'run_id': run, 'payload': DECISIONS}, None),
                (
                    {
                        'action': 'resolve',
                        'run_id': run,
                        'payload': {'finding': 'F1', 'result': 'fixed', 'commit': 'abc123'},
                    },
                    None,
                ),
                ({'action': 'report', 'run_id': run}, None),
                ({'action': 'report', 'run_id': run, 'payload': {'shape': 'comment'}}, None),
                ({'action': 'list'}, None),
            )
        )

        assert added.structured_content['text'] == '5 findings in, 5 recorded: F1, F2, F3, F4, F5\n'
        assert gate.structured_content['text'].splitlines()[0].startswith('F1\tCritical\t[MV-1]')
        assert (
            '2 dispositions recorded; undecided: F3, F4, F5' in disposed.structured_content['text']
        )
        assert resolved.structured_content['text'] == 'F1 fixed\n'
        assert full.structured_content['verdict'] == 'MERGE WITH CONDITIONS'
        assert full.structured_content['text'].startswith('# Review report\n')
        assert comment.structured_content['text'].startswith('## Review\n')
        assert (
            listed.structured_content['text']
            == f'{run}\t-\tdeep\t5 findings\tMERGE WITH CONDITIONS\n'
        )
        assert [path.name for path in directory.iterdir()] == ['MERGE-VADER-REPORT.md']
        assert not any(directory.joinpath(name).exists() for name in FORBIDDEN)

    @pytest.mark.parametrize(
        ('arguments', 'needs'),
        [
            pytest.param({'action': 'start'}, 'start needs a payload', id='start'),
            pytest.param({'action': 'gate'}, 'gate needs run_id', id='gate'),
            pytest.param({'action': 'add', 'run_id': '20260101-000000'}, 'add needs', id='add'),
            pytest.param(
                {'action': 'dispose', 'run_id': '20260101-000000'}, 'dispose needs', id='dispose'
            ),
            pytest.param(
                {'action': 'resolve', 'run_id': '20260101-000000'}, 'resolve needs', id='resolve'
            ),
        ],
    )
    def test_an_action_missing_its_arguments_says_what_it_needs(
        self, arguments: dict[str, object], needs: str
    ) -> None:
        (result,) = asyncio.run(call((arguments, None)))

        assert result.is_error
        assert needs in text_of(result)

    def test_an_anticipated_failure_reaches_the_model_as_its_own_text(self) -> None:
        (result,) = asyncio.run(call(({'action': 'gate', 'run_id': '20260101-000000'}, None)))

        assert result.is_error
        assert 'no review run 20260101-000000; start one first' in text_of(result)

    @pytest.mark.parametrize(
        'payload',
        [
            pytest.param({'persona': 'someone-else'}, id='persona'),
            pytest.param({'persona': 'merge-vader', 'findings': []}, id='finding-list'),
        ],
    )
    def test_add_takes_a_persona_and_no_finding_list(
        self, project: Path, payload: dict[str, object]
    ) -> None:
        run, _ = start(project)

        (result,) = asyncio.run(call(({'action': 'add', 'run_id': run, 'payload': payload}, None)))

        assert result.is_error
