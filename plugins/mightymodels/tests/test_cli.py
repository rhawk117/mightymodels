import pytest
from mightymodels_plugin.cli import build_parser, main
from pytest_mock import MockerFixture


class TestCli:
    def test_help_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            build_parser().parse_args(['--help'])

        assert exit_info.value.code == 0
        assert 'serve' in capsys.readouterr().out

    def test_a_command_is_required(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main([])

        assert exit_info.value.code == 2
        assert 'usage: mightymodels' in capsys.readouterr().err

    def test_serve_starts_the_server(self, mocker: MockerFixture) -> None:
        serve = mocker.patch('mightymodels_plugin.server.serve')

        assert main(['serve']) == 0
        serve.assert_called_once_with()
