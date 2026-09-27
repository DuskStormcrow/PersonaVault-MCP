"""Tool registry skeleton: an allowlist-enforced place for future MCP
tools to be registered. It currently holds none.

This is a governance mechanism, not a security sandbox (Architecture
Contract v0.1, Correction 1): it prevents an unapproved tool name or an
unsafely-shaped schema from being registered by mistake during normal
development. It says nothing about what a fully compromised process
could do through means other than this registry (e.g. dynamically
importing PersonaVault modules directly, bypassing this module
entirely, if PersonaVault happens to be installed in the same
environment).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from .schema_guard import assert_schema_is_safe

# The only tool names this adapter's design contract permits, ever, in
# v0.1 (Architecture Contract v0.1, §2). A name outside this set cannot
# be registered no matter what schema or handler it is paired with.
# Adding a name here is a design decision, not a code change to make
# lightly.
APPROVED_TOOL_NAMES = frozenset({"get_boot_context", "propose_session_note"})


class ToolNotApprovedError(ValueError):
    """Raised when code attempts to register a tool name outside
    APPROVED_TOOL_NAMES."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    input_schema: Mapping[str, object]
    handler: Optional[Callable[..., object]] = None


TOOL_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> None:
    """Register a tool, subject to the name allowlist and schema guard.

    Slice 1 never calls this with a real handler — the registry stays
    empty. The function exists now so its enforcement can be tested
    before any functional tool relies on it.
    """
    if spec.name not in APPROVED_TOOL_NAMES:
        raise ToolNotApprovedError(
            f"Tool name {spec.name!r} is not in APPROVED_TOOL_NAMES; "
            "the architecture contract must be amended before adding it."
        )
    assert_schema_is_safe(spec.input_schema)
    TOOL_REGISTRY[spec.name] = spec


def reset_registry_for_tests() -> None:
    """Test-only helper: clears TOOL_REGISTRY so one test's registration
    cannot leak into another's."""
    TOOL_REGISTRY.clear()
