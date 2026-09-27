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
from .tools import get_boot_context


def register_default_tools() -> None:
    """Register every tool this adapter currently implements.

    As of Slice 2, that is exactly one: get_boot_context.
    propose_session_note is reserved in the name allowlist but has no
    handler and is not registered here.
    """
    register_tool(
        ToolSpec(
            name=get_boot_context.TOOL_NAME,
            input_schema=get_boot_context.INPUT_SCHEMA,
            handler=get_boot_context.handle,
        )
    )
