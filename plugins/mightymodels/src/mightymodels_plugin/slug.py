"""The one name type that may become a path component under `.mightymodels/`."""

from typing import Annotated, override

from pydantic import ConfigDict, RootModel, StringConstraints, ValidationError

from mightymodels_plugin.errors import StateError

SLUG_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9_-]*$'
SLUG_LIMIT = 64

type SlugText = Annotated[str, StringConstraints(pattern=SLUG_PATTERN, max_length=SLUG_LIMIT)]


class InvalidSlugError(StateError):
    def __init__(self, raw: str) -> None:
        super().__init__(
            f'{raw!r} is not a slug: letters, digits, dashes and underscores only, '
            f'starting with a letter or digit, at most {SLUG_LIMIT} characters'
        )
        self.raw = raw


class Slug(RootModel[SlugText]):
    model_config = ConfigDict(frozen=True)

    @override
    def __str__(self) -> str:
        return self.root


def parsed_slug(raw: str) -> Slug | InvalidSlugError:
    try:
        return Slug(raw)
    except ValidationError:
        return InvalidSlugError(raw)
