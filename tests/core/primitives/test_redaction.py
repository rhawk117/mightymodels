import re
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st
from mightymodels_core.primitives import (
    PatternName,
    RedactedTextTooLongError,
    create_secret_patterns,
    redact,
    redact_within,
    redaction_of,
    redaction_within,
)
from mightymodels_core.primitives.redaction import default_secret_patterns

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

LONG_TEXT = 60_000
SECONDS_FOR_LONG_TEXT = 5.0
SOURCE = Path(__file__).parents[3] / 'packages' / 'core' / 'src'
PATTERN_AT_THE_FIRST_RELEASE = re.compile(
    r'(?i)[A-Z0-9_]*(?:password|passwd|secret|token|api[_-]?key)[A-Z0-9_]*'
    r'["\']?\s*[:=]\s*["\']?[^\s,;"\']+'
)
FRAGMENTS = (
    'password',
    'passwd',
    'secret',
    'token',
    'api',
    'key',
    'apikey',
    'api_key',
    'api-key',
    '-',
    '_',
    '=',
    ':',
    ' ',
    '\n',
    ',',
    '"',
    "'",
    'x',
    '7',
    'ſ',
    'K',
)
ASSIGNMENT = 'password=x'
ASSIGNMENT_REDACTED = '[REDACTED:assignment]'


@dataclass(slots=True, kw_only=True, frozen=True)
class SecretSample:
    name: PatternName
    text: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def secret_pattern_cases() -> pytest.MarkDecorator:
    samples = [
        SecretSample(
            name='private-key',
            text='-----BEGIN RSA PRIVATE KEY-----\nabc\ndef\n-----END RSA PRIVATE KEY-----',
        ),
        SecretSample(name='aws-key', text='AKIAIOSFODNN7EXAMPLE'),
        SecretSample(name='github-token', text='ghp_' + 'a' * 36),
        SecretSample(name='slack-token', text='xoxb-1234567890-abcdef'),
        SecretSample(name='stripe-key', text='sk_live_' + 'a' * 16),
        SecretSample(name='api-key', text='sk-ant-' + 'a' * 20),
        SecretSample(name='jwt', text='eyJhbGci.eyJzdWIi.signature'),
        SecretSample(name='bearer', text='Bearer abcdefghijkl1234'),
        SecretSample(name='assignment', text='password=hunter2'),
    ]
    return pytest.mark.parametrize('sample', [sample.param for sample in samples])


def long_token_cases() -> pytest.MarkDecorator:
    tokens = {
        'x': 'x' * LONG_TEXT,
        'digits': '7_' * (LONG_TEXT // 2),
        'token': 'token' * (LONG_TEXT // 5),
        'token-api-key': 'tokenapi-key' * (LONG_TEXT // 12),
        'token-equals': 'token=' * (LONG_TEXT // 6),
        'token-spaces': 'token' + ' ' * LONG_TEXT,
    }
    return pytest.mark.parametrize(
        'token', [pytest.param(token, id=name) for name, token in tokens.items()]
    )


def with_assignment(plain_length: int) -> str:
    return 'a' * plain_length + ' ' + ASSIGNMENT


class TestEachPattern:
    @secret_pattern_cases()
    def test_replaces_the_secret_with_its_marker(self, sample: SecretSample) -> None:
        assert redact(sample.text) == f'[REDACTED:{sample.name}]'

    def test_replaces_url_credentials_and_keeps_the_rest_of_the_url(self) -> None:
        assert redact('https://user:pass@host/path') == (
            'https://[REDACTED:url-credentials]@host/path'
        )

    def test_has_a_sample_for_every_pattern(self) -> None:
        sampled = {case.values[0].name for case in secret_pattern_cases().args[1]}
        sampled.add('url-credentials')

        assert sampled == set(get_args(PatternName.__value__))

    def test_applies_the_patterns_in_the_order_the_old_tree_did(self) -> None:
        assert list(create_secret_patterns().by_name) == [
            'private-key',
            'aws-key',
            'github-token',
            'slack-token',
            'stripe-key',
            'api-key',
            'jwt',
            'bearer',
            'url-credentials',
            'assignment',
        ]

    def test_default_patterns_cannot_be_changed(self) -> None:
        patterns = default_secret_patterns()

        assert not isinstance(patterns.by_name, MutableMapping)
        assert 'add' not in dir(patterns)

    def test_leaves_text_without_a_secret_alone(self) -> None:
        assert redact('nothing to hide here') == 'nothing to hide here'


class TestTheAssignmentPattern:
    texts = st.lists(st.sampled_from(FRAGMENTS), max_size=14).map(''.join)

    @given(text=texts)
    def test_redacts_generated_text_exactly_as_the_pattern_at_the_first_release_did(
        self, text: str
    ) -> None:
        current = create_secret_patterns().by_name['assignment']

        assert current.sub('[R]', text) == PATTERN_AT_THE_FIRST_RELEASE.sub('[R]', text)
        assert [m.span() for m in current.finditer(text)] == [
            m.span() for m in PATTERN_AT_THE_FIRST_RELEASE.finditer(text)
        ]

    @long_token_cases()
    def test_redacts_sixty_thousand_characters_of_one_token_within_seconds(
        self, token: str
    ) -> None:
        started = time.perf_counter()
        redact(token)

        assert time.perf_counter() - started < SECONDS_FOR_LONG_TEXT

    def test_still_redacts_a_prefixed_assignment(self) -> None:
        assert redact('export MY_DB_PASSWORD="hunter2" now') == (
            'export [REDACTED:assignment]" now'
        )


class TestTheHitCount:
    def test_counts_every_match_across_patterns(self) -> None:
        text = 'AKIAIOSFODNN7EXAMPLE then password=a and token=b'

        redaction = redaction_of(text)

        assert redaction.hits == 3
        assert redaction.text == redact(text)

    def test_counts_zero_for_text_without_a_secret(self) -> None:
        assert redaction_of('nothing to hide here').hits == 0


class TestRedactionWithinALimit:
    LIMIT = 64
    GROWTH = len(ASSIGNMENT_REDACTED) - len(ASSIGNMENT)

    def test_keeps_text_that_redaction_brings_to_the_limit(self) -> None:
        text = with_assignment(self.LIMIT - len(ASSIGNMENT_REDACTED) - 1)

        kept = redact_within(text, 'rant', self.LIMIT)

        assert kept == 'a' * (self.LIMIT - len(ASSIGNMENT_REDACTED) - 1) + ' ' + ASSIGNMENT_REDACTED
        assert len(kept) == self.LIMIT

    def test_refuses_text_that_redaction_takes_one_past_it(self) -> None:
        text = with_assignment(self.LIMIT - len(ASSIGNMENT_REDACTED))

        with pytest.raises(RedactedTextTooLongError) as refused:
            redact_within(text, 'rant', self.LIMIT)

        named = (refused.value.field, refused.value.limit, refused.value.length)
        assert named == ('rant', self.LIMIT, self.LIMIT + 1)
        assert str(refused.value) == (
            f'rant: {self.LIMIT + 1} characters once its secrets are redacted, and at most '
            f'{self.LIMIT} are stored; shorten the text; nothing was written'
        )

    def test_returns_the_hit_count_with_the_kept_text(self) -> None:
        text = with_assignment(self.LIMIT - len(ASSIGNMENT_REDACTED) - 1)

        assert redaction_within(text, 'rant', self.LIMIT).hits == 1

    def test_never_cuts_the_text_it_refuses(self) -> None:
        text = with_assignment(self.LIMIT)

        with pytest.raises(RedactedTextTooLongError):
            redact_within(text, 'rant', self.LIMIT)


class TestRedactedTextConstruction:
    def test_redact_is_the_only_constructor_in_the_source(self) -> None:
        constructors = {
            path.name
            for path in SOURCE.rglob('*.py')
            for line in path.read_text().splitlines()
            if 'RedactedText(' in line and 'NewType(' not in line
        }

        assert constructors == {'redaction.py'}
