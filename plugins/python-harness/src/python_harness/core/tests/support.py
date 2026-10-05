"""Emitted JSON documents, decoded for tests that assert on what a command prints."""

import io
import json
from typing import Any

from python_harness.core.output import write_document

type JsonDocument = dict[str, Any]


def emit_document(value: object) -> JsonDocument:
    stream = io.StringIO()
    write_document(value, stream)
    return json.loads(stream.getvalue())
