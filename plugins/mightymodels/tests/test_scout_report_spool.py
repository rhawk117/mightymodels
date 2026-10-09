"""The scout-report spool: files in the data directory that the next state tool call takes in."""

import json
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path

import pytest
from mightymodels_plugin.database import DATABASE_NAME, SCHEMA_VERSION, Database
from mightymodels_plugin.declarative import PROSE_LIMIT
from mightymodels_plugin.tools.similarity.schema import SimilarityKind
from mightymodels_plugin.tools.similarity.spool import (
    REJECTED_DIRECTORY,
    SPOOL_DIRECTORY,
    SPOOL_FILE_BYTES,
    SPOOL_FILES_PER_CALL,
)
from mightymodels_plugin.tools.similarity.tables import ScoutReportRow, SimilarityRow
from mightymodels_plugin.tools.tests.support import (
    StateServer,
    ToolCall,
    repository_key_of,
    text_of,
    tree,
)
from mightymodels_plugin.workspace import Workspace
from sqlalchemy import select

type Report = Mapping[str, object]
type GitRunner = Callable[..., str]

OTHER_KEY = 'acme/gadgets'
REPORT_TEXT = 'the drain loop sleeps between every retry batch'
SEARCH: ToolCall = ('similarity', {'action': 'search', 'query': REPORT_TEXT})
CREDENTIALS = '://a:b@'


def report_for(key: str, **given: object) -> Report:
    return {
        'repository_key': key,
        'scout': 'code-scout',
        'target': 'the drain loop',
        'report': REPORT_TEXT,
    } | given


def spooled(spool: Path, name: str, content: Report | bytes) -> Path:
    spool.mkdir(parents=True, exist_ok=True)
    file = spool.joinpath(name)
    file.write_bytes(content if isinstance(content, bytes) else json.dumps(content).encode())
    return file


def rejected_files(spool: Path) -> list[Path]:
    return sorted(spool.joinpath(REJECTED_DIRECTORY).glob('*'))


def scout_reports(database: Database) -> list[ScoutReportRow]:
    with database.transaction() as session:
        rows = list(session.scalars(select(ScoutReportRow)))
        session.expunge_all()
    return rows


def similarity_kinds(database: Database) -> list[str]:
    with database.transaction() as session:
        return list(session.scalars(select(SimilarityRow.kind)))


@pytest.fixture
def own_key(repository_workspace: Workspace) -> str:
    return repository_key_of(repository_workspace).root


class TestAReportFileOfThisRepository:
    @pytest.fixture
    def after_the_next_call(
        self, own_key: str, spool: Path, state_server: StateServer
    ) -> tuple[Path, str]:
        file = spooled(spool, 'first.json', report_for(own_key))
        (searched,) = state_server.call(SEARCH)
        assert not searched.is_error
        return file, text_of(searched)

    def test_is_gone_from_the_spool(self, after_the_next_call: tuple[Path, str]) -> None:
        assert not after_the_next_call[0].exists()

    def test_is_found_by_the_search_of_that_call(
        self, after_the_next_call: tuple[Path, str]
    ) -> None:
        assert 'scout-report ' in after_the_next_call[1]

    @pytest.mark.usefixtures('after_the_next_call')
    def test_is_a_stored_scout_report_and_a_similarity_row(
        self, repository_database: Database
    ) -> None:
        (stored,) = scout_reports(repository_database)

        assert (stored.scout, stored.target, stored.report) == (
            'code-scout',
            'the drain loop',
            REPORT_TEXT,
        )
        assert similarity_kinds(repository_database) == [SimilarityKind.SCOUT_REPORT]

    def test_is_taken_in_by_any_tool_and_only_once(
        self, own_key: str, spool: Path, state_server: StateServer, repository_database: Database
    ) -> None:
        spooled(spool, 'first.json', report_for(own_key))

        state_server.call(('crashout', {'action': 'stats'}))
        state_server.call(SEARCH)

        assert len(scout_reports(repository_database)) == 1

    def test_has_its_secrets_redacted_before_it_is_stored(
        self, own_key: str, spool: Path, state_server: StateServer, repository_database: Database
    ) -> None:
        leaking = report_for(own_key, report='drain password=hunter2', target='token=abc123')
        spooled(spool, 'leaking.json', leaking)

        state_server.call(SEARCH)
        (stored,) = scout_reports(repository_database)

        assert 'hunter2' not in stored.report
        assert 'abc123' not in stored.target

    def test_several_files_are_taken_in_by_one_call(
        self, own_key: str, spool: Path, state_server: StateServer, repository_database: Database
    ) -> None:
        spooled(spool, 'first.json', report_for(own_key))
        spooled(spool, 'second.json', report_for(own_key, report=f'{REPORT_TEXT}s'))

        state_server.call(SEARCH)

        assert len(scout_reports(repository_database)) == 2

    def test_is_not_taken_in_when_the_call_is_refused_before_it_runs(
        self, own_key: str, spool: Path, state_server: StateServer
    ) -> None:
        file = spooled(spool, 'first.json', report_for(own_key))

        (refused,) = state_server.call(('similarity', {'action': 'delete'}))

        assert refused.is_error
        assert file.exists()


class TestAMalformedFile:
    CASES = (
        pytest.param(b'not json', id='not-json'),
        pytest.param(b'', id='empty'),
        pytest.param(b'\xff\xfe', id='not-text'),
        pytest.param(b'[]', id='not-an-object'),
        pytest.param(json.dumps(report_for(OTHER_KEY, report='  ')).encode(), id='blank-report'),
        pytest.param(json.dumps(report_for(OTHER_KEY, scout='primary')).encode(), id='other-scout'),
        pytest.param(json.dumps(report_for(OTHER_KEY, extra=1)).encode(), id='extra-field'),
        pytest.param(json.dumps(report_for('../../escape')).encode(), id='key-with-separators'),
        pytest.param(json.dumps(report_for('')).encode(), id='empty-key'),
        pytest.param(
            json.dumps(report_for(OTHER_KEY, report='x' * (PROSE_LIMIT + 1))).encode(),
            id='report-over-its-column',
        ),
        pytest.param(b' ' * (SPOOL_FILE_BYTES + 1), id='over-the-file-size'),
    )

    @pytest.fixture
    def beside_a_good_file(
        self,
        request: pytest.FixtureRequest,
        own_key: str,
        spool: Path,
        state_server: StateServer,
    ) -> tuple[Path, bytes, bool]:
        file = spooled(spool, 'a-bad.json', request.param)
        spooled(spool, 'b-good.json', report_for(own_key))
        (searched,) = state_server.call(SEARCH)
        return file, request.param, searched.is_error

    @pytest.mark.parametrize('beside_a_good_file', CASES, indirect=True)
    def test_is_set_aside_with_its_bytes_and_the_call_succeeds(
        self, beside_a_good_file: tuple[Path, bytes, bool], spool: Path
    ) -> None:
        file, content, is_error = beside_a_good_file

        assert not is_error
        assert not file.exists()
        assert [kept.read_bytes() for kept in rejected_files(spool)] == [content]

    @pytest.mark.parametrize('beside_a_good_file', CASES, indirect=True)
    @pytest.mark.usefixtures('beside_a_good_file')
    def test_does_not_keep_the_good_file_beside_it_from_being_taken_in(
        self, spool: Path, repository_database: Database
    ) -> None:
        assert not spool.joinpath('b-good.json').exists()
        assert len(scout_reports(repository_database)) == 1

    @pytest.mark.parametrize('beside_a_good_file', CASES[:1], indirect=True)
    @pytest.mark.usefixtures('beside_a_good_file')
    def test_is_kept_under_a_name_of_its_own_beside_one_set_aside_before(
        self, spool: Path, state_server: StateServer
    ) -> None:
        spooled(spool, 'a-bad.json', b'not json again')

        state_server.call(SEARCH)

        assert sorted(kept.read_bytes() for kept in rejected_files(spool)) == [
            b'not json',
            b'not json again',
        ]

    def test_with_text_that_redaction_lengthens_past_its_column_is_set_aside(
        self, own_key: str, spool: Path, state_server: StateServer, repository_database: Database
    ) -> None:
        lengthened = 'x' * (PROSE_LIMIT - len(CREDENTIALS)) + CREDENTIALS
        file = spooled(spool, 'long.json', report_for(own_key, report=lengthened))

        (searched,) = state_server.call(SEARCH)

        assert not searched.is_error
        assert not file.exists()
        assert len(rejected_files(spool)) == 1
        assert scout_reports(repository_database) == []


class TestAFileOfAnotherRepository:
    @pytest.fixture
    def gadgets(self, tmp_path: Path, data_directory: Path, git: GitRunner) -> StateServer:
        checkout = tmp_path.joinpath('gadgets')
        checkout.mkdir()
        git(checkout, 'init', '--quiet')
        git(checkout, 'remote', 'add', 'origin', 'git@github.com:acme/gadgets.git')
        return StateServer(root=checkout, data_directory=data_directory)

    @pytest.fixture
    def file_of_the_other(self, spool: Path) -> tuple[Path, bytes]:
        file = spooled(spool, 'other.json', report_for(OTHER_KEY))
        return file, file.read_bytes()

    @pytest.fixture
    def after_the_next_call(
        self, file_of_the_other: tuple[Path, bytes], state_server: StateServer
    ) -> tuple[Path, bytes]:
        state_server.call(SEARCH)
        return file_of_the_other

    def test_is_left_where_it_is_as_it_was(self, after_the_next_call: tuple[Path, bytes]) -> None:
        file, content = after_the_next_call

        assert file.read_bytes() == content

    @pytest.mark.usefixtures('after_the_next_call')
    def test_is_not_stored_for_this_repository(
        self, repository_database: Database, spool: Path
    ) -> None:
        assert scout_reports(repository_database) == []
        assert not spool.joinpath(REJECTED_DIRECTORY).exists()

    def test_is_taken_in_by_the_server_of_that_repository(
        self, after_the_next_call: tuple[Path, bytes], gadgets: StateServer
    ) -> None:
        gadgets.call(SEARCH)

        assert not after_the_next_call[0].exists()


class TestNoRepositoryKeyIsEverInAPath:
    @pytest.fixture
    def after_every_kind_of_file(
        self, own_key: str, spool: Path, state_server: StateServer, data_directory: Path
    ) -> list[str]:
        spooled(spool, 'own.json', report_for(own_key))
        spooled(spool, 'other.json', report_for(OTHER_KEY))
        spooled(spool, 'traversal.json', report_for('../../escape'))
        spooled(spool, 'garbage.json', b'garbage')
        state_server.call(SEARCH)
        return sorted(tree(data_directory.parent))

    def test_a_path_holds_the_data_directory_and_fixed_names_and_nothing_a_file_says(
        self, after_every_kind_of_file: list[str], own_key: str
    ) -> None:
        paths = ' '.join(after_every_kind_of_file)

        assert 'escape' not in paths
        assert own_key.removeprefix('local:') not in paths
        assert 'gadgets' not in paths.replace('other.json', '')

    def test_the_file_naming_a_traversal_is_set_aside_inside_the_spool(
        self, after_every_kind_of_file: list[str], data_directory: Path
    ) -> None:
        set_aside = [path for path in after_every_kind_of_file if path.endswith('traversal.json')]

        assert len(set_aside) == 1
        assert Path(set_aside[0]).parent.parts[-2:] == (SPOOL_DIRECTORY, REJECTED_DIRECTORY)
        assert Path(set_aside[0]).parent.parent.parent.name == data_directory.name


class TestAFileThatIsNotARegularFile:
    def test_a_symlink_and_a_directory_are_left_alone(
        self, own_key: str, spool: Path, state_server: StateServer, tmp_path: Path
    ) -> None:
        outside = tmp_path.joinpath('outside.json')
        outside.write_text(json.dumps(report_for(own_key)), encoding='utf-8')
        spool.mkdir(parents=True)
        spool.joinpath('link.json').symlink_to(outside)
        spool.joinpath('directory.json').mkdir()

        (searched,) = state_server.call(SEARCH)

        assert not searched.is_error
        assert spool.joinpath('link.json').is_symlink()
        assert spool.joinpath('directory.json').is_dir()
        assert outside.exists()

    def test_a_file_that_does_not_end_in_json_is_not_read(
        self, own_key: str, spool: Path, state_server: StateServer
    ) -> None:
        file = spooled(spool, 'half-written.tmp', report_for(own_key))

        state_server.call(SEARCH)

        assert file.exists()


class TestTheBoundOnAFileCount:
    @pytest.fixture
    def more_files_than_a_call_takes(self, own_key: str, spool: Path) -> int:
        count = SPOOL_FILES_PER_CALL + 2
        for number in range(count):
            spooled(
                spool, f'{number:04}.json', report_for(own_key, report=f'{REPORT_TEXT} {number}')
            )
        return count

    def test_a_call_takes_in_that_many_and_the_next_call_the_rest(
        self,
        more_files_than_a_call_takes: int,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        state_server.call(('crashout', {'action': 'stats'}))
        after_one = len(scout_reports(repository_database))
        state_server.call(('crashout', {'action': 'stats'}))

        assert after_one == SPOOL_FILES_PER_CALL
        assert len(scout_reports(repository_database)) == more_files_than_a_call_takes
        assert list(spool.glob('*.json')) == []


class TestWhereNothingIsToBeTakenIn:
    def test_a_call_creates_no_spool(
        self, connected_server: StateServer, data_directory: Path, spool: Path
    ) -> None:
        connected_server.call(('crashout', {'action': 'stats'}), SEARCH)

        assert not spool.exists()
        assert sorted(tree(data_directory)) <= sorted(
            {DATABASE_NAME, f'{DATABASE_NAME}-wal', f'{DATABASE_NAME}-shm'}
        )


class TestAFileOfAnotherSchemaVersion:
    @pytest.fixture
    def refused_with_a_report_waiting(
        self, own_key: str, spool: Path, data_directory: Path
    ) -> dict[str, bytes]:
        data_directory.mkdir()
        with closing(sqlite3.connect(data_directory.joinpath(DATABASE_NAME))) as connection:
            connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION + 1}')
        spooled(spool, 'first.json', report_for(own_key))
        return tree(data_directory)

    def test_leaves_the_database_and_the_spool_as_they_were(
        self,
        refused_with_a_report_waiting: dict[str, bytes],
        state_server: StateServer,
        data_directory: Path,
    ) -> None:
        (refused,) = state_server.call(SEARCH)

        assert refused.is_error
        assert tree(data_directory) == refused_with_a_report_waiting
