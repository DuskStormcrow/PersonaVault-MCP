"""Item 20 (Slice 3) / item 14 (Slice 2): the tool registry contains
exactly the tools this adapter currently implements -- one in Slice 2,
two as of Slice 3 -- and nothing else."""

from __future__ import annotations

import pytest

from personavault_mcp.bootstrap import register_default_tools
from personavault_mcp.registry import TOOL_REGISTRY, reset_registry_for_tests
from personavault_mcp.tools import get_boot_context, propose_session_note


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


def test_exactly_two_functional_tools_registered() -> None:
    register_default_tools()
    assert len(TOOL_REGISTRY) == 2
    assert set(TOOL_REGISTRY) == {"get_boot_context", "propose_session_note"}


def test_registered_get_boot_context_has_its_own_handler() -> None:
    register_default_tools()
    spec = TOOL_REGISTRY["get_boot_context"]
    assert spec.handler is get_boot_context.handle
    assert spec.input_schema == get_boot_context.INPUT_SCHEMA


def test_registered_propose_session_note_has_its_own_handler() -> None:
    register_default_tools()
    spec = TOOL_REGISTRY["propose_session_note"]
    assert spec.handler is propose_session_note.handle
    assert spec.input_schema == propose_session_note.INPUT_SCHEMA


def test_no_third_tool_exists_to_register() -> None:
    """There is no reserved name beyond the two approved ones -- nothing
    for a future accidental registration to reach even if attempted."""
    from personavault_mcp.registry import APPROVED_TOOL_NAMES

    assert APPROVED_TOOL_NAMES == {"get_boot_context", "propose_session_note"}


def test_registering_default_tools_twice_stays_at_two() -> None:
    register_default_tools()
    register_default_tools()
    assert len(TOOL_REGISTRY) == 2
