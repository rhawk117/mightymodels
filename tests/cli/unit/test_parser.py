import pytest
from mightymodels_cli.main import build_parser, main

pytestmark = pytest.mark.unit

SLUG = 'port-cli'


def refused_verify_run_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'arguments',
        [
            pytest.param(['--slug', SLUG], id='neither-ids-nor-all'),
            pytest.param(['--slug', SLUG, '--id', 'I1', '--all'], id='ids-and-all'),
            pytest.param(['--all'], id='no-slug'),
            pytest.param(['--slug', SLUG, '--all', '--phase', 'shipping'], id='unknown-phase'),
        ],
    )


class TestCli:
    def test_help_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            build_parser().parse_args(['--help'])

        assert exit_info.value.code == 0
        assert 'verify' in capsys.readouterr().out

    def test_a_command_is_required(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main([])

        assert exit_info.value.code == 2
        assert 'usage: mightymodels' in capsys.readouterr().err


class TestVerifyRun:
    options = ('--slug', '--id', '--all', '--phase')

    def test_help_shows_its_options(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['verify', 'run', '--help'])

        shown = capsys.readouterr().out
        assert exit_info.value.code == 0
        assert [option in shown for option in self.options] == [True] * 4

    @refused_verify_run_cases()
    def test_refuses_a_command_line_it_does_not_define(
        self, arguments: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['verify', 'run', *arguments])

        assert exit_info.value.code == 2
        assert 'usage: mightymodels verify run' in capsys.readouterr().err
