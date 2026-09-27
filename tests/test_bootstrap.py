"""Item 14: the tool registry contains exactly one functional tool after
Slice 2 registration, and no second tool is registered alongside it."""

from __future__ import annotations

import pytest

from personavault_mcp.bootstrap import register_default_tools
from personavault_mcp.registry import TOOL_REGISTRY, reset_registry_for_tests
from personavault_mcp.tools import get_boot_context


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


def test_exactly_one_functional_tool_registered() -> None:
    register_default_tools()
    assert len(TOOL_REGISTRY) == 1
    assert set(TOOL_REGISTRY) == {"get_boot_context"}


def test_registered_tool_is_get_boot_context_with_its_own_handler() -> None:
    register_default_tools()
    spec = TOOL_REGISTRY["get_boot_context"]
    assert spec.handler is get_boot_context.handle
    assert spec.input_schema == get_boot_context.INPUT_SCHEMA


def test_propose_session_note_is_not_registered() -> None:
    register_default_tools()
    assert "propose_session_note" not in TOOL_REGISTRY


def test_registering_default_tools_twice_stays_at_one() -> None:
    register_default_tools()
    register_default_tools()
    assert len(TOOL_REGISTRY) == 1
