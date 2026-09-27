"""Guards a tool's input schema against shapes that would let a host
smuggle in capabilities the architecture contract forbids — most
importantly, an arbitrary filesystem path, or an unconstrained payload
that could carry unlisted fields (such as a ``decision`` field on a
proposal tool).

Checked once, here, so every future tool benefits from the same guard
rather than each tool author reinventing it.
"""

from __future__ import annotations

from typing import Mapping

_DENIED_PROPERTY_NAME_HINTS = (
    "path",
    "filepath",
    "file_path",
    "filename",
    "dir",
    "directory",
    "root",
    "location",
)


class UnsafeToolSchemaError(ValueError):
    """Raised when a tool input schema is shaped unsafely for this
    adapter's contract."""


def assert_schema_is_safe(schema: Mapping[str, object]) -> None:
    """Raise ``UnsafeToolSchemaError`` if a tool input schema accepts
    arbitrary unlisted fields, or looks like it accepts a raw filesystem
    path from a host.
    """
    if schema.get("additionalProperties", False):
        raise UnsafeToolSchemaError(
            "Tool input schemas must not set additionalProperties: true — "
            "an MCP caller must never be able to smuggle in unlisted fields "
            "(e.g. a 'decision' field on a proposal tool)."
        )

    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise UnsafeToolSchemaError("Tool input schema 'properties' must be a mapping.")

    for property_name in properties:
        lowered = property_name.lower()
        if any(hint in lowered for hint in _DENIED_PROPERTY_NAME_HINTS):
            raise UnsafeToolSchemaError(
                f"Tool input schema property {property_name!r} looks like a "
                "raw filesystem path field, which no v0.1 tool may accept."
            )
