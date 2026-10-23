"""Builders and shared values for the snapshot tests."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mightymodels_core.contract import Receipt
from mightymodels_core.primitives import redact
from mightymodels_core.reviews import IncomingFinding

if TYPE_CHECKING:
    from mightymodels_core.schemas.contract import Outcome

HEAD = 'a' * 40
MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)


def create_receipt(key: str, *, outcome: Outcome, head: str) -> Receipt:
    return Receipt(
        key=key,
        argv=('pytest', '-q', key),
        outcome=outcome,
        exit=0,
        duration_ms=5,
        stdout_tail=redact(''),
        stderr_tail=redact(''),
        digest='digest',
        head=head,
        phase='task',
        at=MOMENT,
    )


def create_defect(source: str) -> IncomingFinding:
    return IncomingFinding(
        sources=(source,),
        severity='High',
        kind='defect',
        security=False,
        title=f'defect found by {source}',
        location=f'src/{source}.py:10',
        fix='fix it',
        verify='pytest -q',
        evidence=None,
    )
