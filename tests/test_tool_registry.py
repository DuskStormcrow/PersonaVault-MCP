"""Tests for the tool registry skeleton: the registry must currently be
empty, and the allowlist/schema-guard mechanism must actually reject
what it claims to reject — proven with synthetic specs, since no real
tool exists yet in Slice 1.
"""

from __future__ import annotations

import pytest

from personavault_mcp.registry import (
    APPROVED_TOOL_NAMES,
    TOOL_REGISTRY,
    ToolNotApprovedError,
    ToolSpec,
    register_tool,
    reset_registry_for_tests,
)
from personavault_mcp.schema_guard import UnsafeToolSchemaError

SAFE_SCHEMA = {
    "type": "object",
    "properties": {"persona": {"type": "string"}},
    "required": ["persona"],
    "additionalProperties": False,
}


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


# Item 8: tool registration is currently empty.
def test_registry_is_empty_by_default() -> None:
    assert TOOL_REGISTRY == {}


def test_approved_tool_names_reserved_but_unregistered() -> None:
    """The two future tool names are reserved in the allowlist so a
    later slice can register them, but nothing has registered them yet."""
    assert APPROVED_TOOL_NAMES == {"get_boot_context", "propose_session_note"}
    assert set(TOOL_REGISTRY) == set()


# Item 9: unknown/unapproved tool registration must fail.
@pytest.mark.parametrize(
    "unapproved_name",
    ["commit_intake", "delete_persona", "update_persona", "read_corelog", "anything_else"],
)
def test_unapproved_tool_name_is_rejected(unapproved_name: str) -> None:
    with pytest.raises(ToolNotApprovedError):
        register_tool(ToolSpec(name=unapproved_name, input_schema=SAFE_SCHEMA))
    assert unapproved_name not in TOOL_REGISTRY


def test_approved_tool_name_with_safe_schema_registers_successfully() -> None:
    """Proves the allowlist mechanism itself works end to end, using a
    synthetic handler — this is a registry test, not an implementation
    of get_boot_context."""
    register_tool(ToolSpec(name="get_boot_context", input_schema=SAFE_SCHEMA, handler=None))
    assert "get_boot_context" in TOOL_REGISTRY


@pytest.mark.parametrize(
    "unsafe_property_name",
    ["path", "file_path", "filepath", "directory", "root", "location"],
)
def test_approved_name_with_path_like_property_is_rejected(unsafe_property_name: str) -> None:
    unsafe_schema = {
        "type": "object",
        "properties": {unsafe_property_name: {"type": "string"}},
        "additionalProperties": False,
    }
    with pytest.raises(UnsafeToolSchemaError):
        register_tool(ToolSpec(name="get_boot_context", input_schema=unsafe_schema))
    assert "get_boot_context" not in TOOL_REGISTRY


def test_approved_name_with_additional_properties_true_is_rejected() -> None:
    unsafe_schema = {
        "type": "object",
        "properties": {"persona": {"type": "string"}},
        "additionalProperties": True,
    }
    with pytest.raises(UnsafeToolSchemaError):
        register_tool(ToolSpec(name="get_boot_context", input_schema=unsafe_schema))
    assert "get_boot_context" not in TOOL_REGISTRY
