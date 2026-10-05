"""Reading and parsing sources into parsed or unparsable outcomes."""

from types import MappingProxyType

import pytest
from python_harness.core.sources import (
    ParsedModule,
    SourceFile,
    UnparsableSource,
    load_source,
    load_sources,
    parse_source,
)
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.workspace import Workspace


class TestParseSource:
    @pytest.mark.parametrize(
        ('text', 'outcome_type'),
        [
            pytest.param('value = 1\n', ParsedModule, id='valid'),
            pytest.param('def broken(:\n', UnparsableSource, id='syntax-error'),
        ],
    )
    def test_outcome_type_follows_syntax(self, text: str, outcome_type: type) -> None:
        outcome = parse_source(SourceFile('module.py', text))

        assert isinstance(outcome, outcome_type)

    def test_unparsable_source_keeps_the_error_line(self) -> None:
        outcome = parse_source(SourceFile('module.py', 'ok = 1\ndef broken(:\n'))

        assert outcome == UnparsableSource('module.py', 2, 'invalid syntax')


class TestSourceFile:
    SOURCE = SourceFile('module.py', 'first\nsecond\nthird\n')

    @pytest.mark.parametrize(
        ('start', 'end', 'expected'),
        [
            pytest.param(1, 1, ('first',), id='single-line'),
            pytest.param(2, 3, ('second', 'third'), id='range'),
            pytest.param(3, 9, ('third',), id='clipped-at-end'),
        ],
    )
    def test_line_range_is_one_based_and_inclusive(
        self, start: int, end: int, expected: tuple[str, ...]
    ) -> None:
        assert self.SOURCE.line_range(start, end) == expected


class TestLoadSources:
    FILES = MappingProxyType(
        {
            'pkg/good.py': 'value = 1\n',
            'pkg/bad.py': 'def broken(:\n',
            'pkg/latin.py': '# -*- coding: latin-1 -*-\nname = "caf\xe9"\n',
            'pkg/raw.py': 'name = "caf\xe9"\n',
        }
    )

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        workspace = project_builder.write({})
        for relative, text in self.FILES.items():
            target = workspace.root.joinpath(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode('latin-1'))
        return workspace

    def test_partitions_parsed_and_unparsable_modules(self, workspace: Workspace) -> None:
        loaded = load_sources(workspace, workspace.python_files('pkg'))

        parsed = tuple(module.source.path for module in loaded.modules)
        unparsable = tuple(item.path for item in loaded.unparsable)
        assert (parsed, unparsable) == (
            ('pkg/good.py', 'pkg/latin.py'),
            ('pkg/bad.py', 'pkg/raw.py'),
        )

    def test_honours_the_encoding_cookie(self, workspace: Workspace) -> None:
        loaded = load_sources(workspace, workspace.python_files('pkg/latin.py'))

        assert 'caf\xe9' in loaded.modules[0].source.text


class TestLoadSource:
    PATH = 'pkg/module.py'

    @pytest.fixture
    def workspace(
        self, project_builder: ProjectBuilder, request: pytest.FixtureRequest
    ) -> Workspace:
        workspace = project_builder.write({})
        target = workspace.root.joinpath(self.PATH)
        target.parent.mkdir(parents=True)
        target.write_bytes(request.param)
        return workspace

    @pytest.fixture
    def dangling_link(self, project_builder: ProjectBuilder) -> Workspace:
        workspace = project_builder.write({'pkg/__init__.py': ''})
        link = workspace.root.joinpath(self.PATH)
        link.symlink_to(workspace.root.joinpath('pkg/missing.py'))
        return workspace

    @pytest.mark.parametrize(
        'workspace',
        [
            pytest.param(b'name = "caf\xe9"\n', id='invalid-utf8-without-a-cookie'),
            pytest.param(
                b'first = 1\nsecond = 2\nname = "caf\xe9"\n',
                id='invalid-utf8-without-a-cookie-past-the-cookie-lines',
            ),
            pytest.param(
                b'# -*- coding: no-such-codec -*-\nvalue = 1\n',
                id='cookie-naming-an-unknown-codec',
            ),
            pytest.param(
                b'# -*- coding: ascii -*-\nname = "caf\xe9"\n',
                id='undecodable-bytes-under-a-valid-cookie',
            ),
        ],
        indirect=True,
    )
    def test_undecodable_file_is_unparsable_without_a_line(self, workspace: Workspace) -> None:
        outcome = load_source(workspace, workspace.resolve(self.PATH))

        assert isinstance(outcome, UnparsableSource)
        assert (outcome.path, outcome.line) == (self.PATH, None)

    def test_unreadable_file_is_unparsable(self, dangling_link: Workspace) -> None:
        outcome = load_source(dangling_link, dangling_link.root.joinpath(self.PATH))

        assert isinstance(outcome, UnparsableSource)
        assert outcome.line is None
