import pytest
from vibe_code_cli.cli import GROUPS, build_parser, main


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(['--help'])

    assert exit_info.value.code == 0
    assert 'vibe-code' in capsys.readouterr().out


def test_main_without_a_group_prints_usage_and_fails(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert 'usage: vibe-code' in capsys.readouterr().err


def test_help_lists_the_six_groups(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(['--help'])

    output = capsys.readouterr().out
    for group in ('skill', 'hook', 'subagent', 'instruction', 'mcp', 'plugin'):
        assert group in output


def test_parser_accepts_exactly_the_six_groups() -> None:
    assert set(GROUPS) == {'skill', 'hook', 'subagent', 'instruction', 'mcp', 'plugin'}


@pytest.mark.parametrize(
    'old_name',
    [
        'create-skill',
        'create-hooks',
        'create-subagent',
        'create-instructions',
        'create-mcp',
        'plan-plugin',
    ],
)
def test_old_group_names_fail_as_invalid_choices(
    old_name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([old_name, 'validate', '--help'])

    assert exit_info.value.code == 2
    assert 'invalid choice' in capsys.readouterr().err
