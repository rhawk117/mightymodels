import pytest
from mightymodels_hooks.push_command import names_a_push


class TestPushes:
    @pytest.mark.parametrize(
        'command',
        [
            'git push',
            'git push origin main',
            '/usr/bin/git push',
            'git -C repo push',
            'git -c user.name=x push',
            'git $OPTIONS push',
            'cd repo && git push',
            'make; git push',
            'echo hi | git push',
            '(git push)',
            '$(git push)',
            '`git push`',
            'FOO=1 git push',
            'sudo git push',
            'env git push',
            'xargs git push',
            "bash -c 'git push'",
            'sh -lc "git push origin"',
            'eval git push',
            'echo "$(git push)"',
            'make \\\n && git push',
            "git push 'unclosed",
        ],
    )
    def test_command_that_pushes_is_found(self, command: str) -> None:
        assert names_a_push(command)


class TestNoPush:
    @pytest.mark.parametrize(
        'command',
        [
            '',
            'git status',
            'echo "git push"',
            'git pushd',
            'git stash push',
            'git commit -m "git push later"',
            "bash -c 'git status'",
            'ls push',
            'git',
            "echo 'unclosed",
        ],
    )
    def test_command_that_does_not_push_is_passed(self, command: str) -> None:
        assert not names_a_push(command)
