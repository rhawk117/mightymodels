"""Pure file helpers every concept shares: OS error wording, `.python-version` pins."""

COMMENT_PREFIX = '#'
MAX_PIN_CHARACTERS = 64


def describe_os_error(error: OSError) -> str:
    return error.strerror or type(error).__name__


def parse_version_pin(text: str) -> str | None:
    lines = (line.strip() for line in text.splitlines())
    pins = (line for line in lines if line and not line.startswith(COMMENT_PREFIX))
    pin = next(pins, None)
    if pin is None:
        return None
    return pin[:MAX_PIN_CHARACTERS]
