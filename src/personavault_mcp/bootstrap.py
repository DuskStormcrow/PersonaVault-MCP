"""Explicit tool registration entry point.

Importing ``personavault_mcp`` never registers anything by itself --
that would make ``import personavault_mcp`` a side-effecting action,
which conflicts with the stateless, inert-until-asked-for design this
package has held since Slice 1. Whatever eventually starts a real
transport (not part of Slice 2) must call ``register_default_tools()``
explicitly, exactly as this slice's own tests do.
"""

from __future__ import annotations

from .registry import ToolSpec, register_tool
from .tools import get_boot_context, propose_session_note


def register_default_tools() -> None:
    """Register every tool this adapter currently implements.

    As of Slice 3, that is exactly two: get_boot_context (read-only) and
    propose_session_note (write-adjacent, proposal-only -- it can never
    reach commit_session_intake). Nothing else is registered; there is no
    third reserved name to add without a further contract amendment.
    """
    register_tool(
        ToolSpec(
            name=get_boot_context.TOOL_NAME,
            input_schema=get_boot_context.INPUT_SCHEMA,
            handler=get_boot_context.handle,
        )
    )
    register_tool(
        ToolSpec(
            name=propose_session_note.TOOL_NAME,
            input_schema=propose_session_note.INPUT_SCHEMA,
            handler=propose_session_note.handle,
        )
    )
