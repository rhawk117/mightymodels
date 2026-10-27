"""The session pointer repository contract against the sqlite store."""

from datetime import timedelta
from typing import TYPE_CHECKING

from mightymodels_core.session_pointers import POINTER_RETENTION

from tests.core.session_pointers.session_pointers_builders import NOW

if TYPE_CHECKING:
    from tests.core.session_pointers.session_pointers_builders import PointersAt

KEY = 'owner/repo'


class TestSqliteSessionPointerRepository:
    def test_lookup_returns_what_was_recorded(self, pointers_at: PointersAt) -> None:
        pointers = pointers_at(KEY, NOW)
        pointers.record('session-1', 'ticket', 'port-hooks')

        pointer = pointers.lookup('session-1')

        assert pointer is not None
        assert (pointer.kind, pointer.key, pointer.written_at) == ('ticket', 'port-hooks', NOW)

    def test_last_write_wins_per_session(self, pointers_at: PointersAt) -> None:
        pointers_at(KEY, NOW).record('session-1', 'ticket', 'port-hooks')
        later = pointers_at(KEY, NOW + timedelta(hours=1))
        later.record('session-1', 'investigation', 'inv-7')

        pointer = later.lookup('session-1')

        assert pointer is not None
        assert (pointer.kind, pointer.key) == ('investigation', 'inv-7')
        assert pointer.written_at == NOW + timedelta(hours=1)

    def test_other_session_finds_nothing(self, pointers_at: PointersAt) -> None:
        pointers = pointers_at(KEY, NOW)
        pointers.record('session-1', 'ticket', 'port-hooks')

        assert pointers.lookup('session-2') is None

    def test_other_repository_finds_nothing(self, pointers_at: PointersAt) -> None:
        pointers_at(KEY, NOW).record('session-1', 'ticket', 'port-hooks')

        assert pointers_at('owner/other', NOW).lookup('session-1') is None

    def test_prune_deletes_old_pointers_and_keeps_newer_ones(self, pointers_at: PointersAt) -> None:
        pointers_at(KEY, NOW - POINTER_RETENTION - timedelta(seconds=1)).record(
            'old', 'ticket', 'stale'
        )
        pointers_at(KEY, NOW - POINTER_RETENTION).record('edge', 'ticket', 'edge')
        pointers_at(KEY, NOW - timedelta(days=1)).record('new', 'ticket', 'fresh')
        pointers = pointers_at(KEY, NOW)

        deleted = pointers.prune()

        assert deleted == 1
        assert pointers.lookup('old') is None
        assert pointers.lookup('edge') is not None
        assert pointers.lookup('new') is not None
