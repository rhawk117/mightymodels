from hypothesis import example, given
from mightymodels_core.git import SAFE_REVISION, UnsafeRevisionError, revision_error

from tests.core.git.git_builders import PLAIN_NAMES, REFUSED_REVISIONS


class TestRevisionError:
    plain_names = PLAIN_NAMES
    refused_revisions = REFUSED_REVISIONS

    @given(revision=refused_revisions)
    @example(revision='main\n')
    @example(revision='\nmain')
    @example(revision='--output=/tmp/pwned')
    @example(revision='-b')
    @example(revision='.hidden')
    @example(revision='/absolute')
    @example(revision='main branch')
    @example(revision='main;id')
    @example(revision='main^{commit}')
    @example(revision='')
    def test_anything_but_a_whole_plain_name_is_refused(self, revision: str) -> None:
        refusal = revision_error(revision)

        assert isinstance(refusal, UnsafeRevisionError)
        assert refusal.revision == revision

    @given(revision=plain_names)
    @example(revision='main')
    @example(revision='HEAD')
    @example(revision='origin/fix/retry-queue')
    @example(revision='v1.0.0-rc_1')
    @example(revision='a' * 40)
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
