"""PersonaVault MCP Adapter.

Host-neutral sibling component that will expose a bounded, read/propose-only
MCP tool surface over PersonaVault. PersonaVault Core is never modified by
this package and is only ever used as an imported dependency, never the
other way around.

Slice 1 status: skeleton only. No functional MCP tools are registered yet;
`personavault_mcp.registry.TOOL_REGISTRY` is empty. See
docs/ARCHITECTURE_CONTRACT_V0_1.md for the full design contract.
"""

from .server_metadata import ADAPTER_NAME, ADAPTER_VERSION

__all__ = ["ADAPTER_NAME", "ADAPTER_VERSION"]
