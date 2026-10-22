"""Builders the finding check and merge tests share."""

from dataclasses import replace

from mightymodels_core.primitives import redact
from mightymodels_core.reviews import (
    FindingRecord,
    IncomingFinding,
    ReviewOptions,
    fold_findings,
)


def incoming_finding(**changes: object) -> IncomingFinding:
    finding = IncomingFinding(
        sources=('UB-1',),
        severity='High',
        kind='defect',
        security=False,
        title='Unchecked input',
        location='src/q.py:10-20',
        fix='Check it',
        verify='Run the tests',
        evidence=None,
    )
    return replace(finding, **changes)


def held_finding(key: str, **changes: object) -> FindingRecord:
    record = FindingRecord(
        key=key,
        sources=('MV-1',),
        severity='High',
        kind='defect',
        security=False,
        title=redact('Held title'),
        location=redact('src/q.py:10-20'),
        fix=redact('Held fix'),
        verify=redact('Held verify'),
        evidence=None,
        conflict=None,
    )
    return replace(record, **changes)


def fold_one(held: list[FindingRecord], finding: IncomingFinding) -> list[FindingRecord]:
    return fold_findings(held, [finding], ReviewOptions().findings)
