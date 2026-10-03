import pytest
from ai_engineer_cli.cli import build_parser, main


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(['--help'])

    assert exit_info.value.code == 0
    assert 'ai-engineer' in capsys.readouterr().out


def test_main_without_a_group_prints_usage_and_fails(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert 'usage: ai-engineer' in capsys.readouterr().err
