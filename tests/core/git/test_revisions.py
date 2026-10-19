import pytest
from mightymodels_core.git import SAFE_REVISION, UnsafeRevisionError, revision_error


def hostile_revision_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'revision',
        [
            pytest.param('main\n', id='trailing-newline'),
            pytest.param('\nmain', id='leading-newline'),
            pytest.param('--output=/tmp/pwned', id='option'),
            pytest.param('-b', id='leading-dash'),
            pytest.param('.hidden', id='leading-dot'),
            pytest.param('/absolute', id='leading-slash'),
            pytest.param('main branch', id='space'),
            pytest.param('main;id', id='shell-separator'),
            pytest.param('main^{commit}', id='revision-syntax'),
            pytest.param('', id='empty'),
        ],
    )


def plain_revision_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'revision',
        [
            pytest.param('main', id='branch'),
            pytest.param('HEAD', id='head'),
            pytest.param('origin/fix/retry-queue', id='remote-branch'),
            pytest.param('v1.0.0-rc_1', id='tag'),
            pytest.param('a' * 40, id='sha'),
        ],
    )


class TestRevisionError:
    @hostile_revision_cases()
    def test_anything_but_a_whole_plain_name_is_refused(self, revision: str) -> None:
        refusal = revision_error(revision)

        assert isinstance(refusal, UnsafeRevisionError)
        assert refusal.revision == revision

    @plain_revision_cases()
    def test_a_plain_name_is_accepted(self, revision: str) -> None:
        assert revision_error(revision) is None

    def test_the_first_unsafe_name_of_several_is_named(self) -> None:
        refusal = revision_error('main', 'HEAD\n', '--all')

        assert isinstance(refusal, UnsafeRevisionError)
        assert refusal.revision == 'HEAD\n'

    def test_no_names_are_accepted(self) -> None:
        assert revision_error() is None

    def test_the_pattern_is_anchored_by_fullmatch(self) -> None:
        assert SAFE_REVISION.fullmatch('main\n') is None
