"""Inert adapter/server identity metadata.

No functional behavior lives here. This module exists so the adapter can
state what it is and what it is designed to be compatible with, before any
MCP tool or transport is implemented.
"""

from __future__ import annotations

ADAPTER_NAME = "personavault-mcp-adapter"
ADAPTER_VERSION = "0.1.0"

# The MCP protocol version this adapter is built against. Negotiated at
# connection time once a real transport exists — not in Slice 1.
MCP_PROTOCOL_VERSION_TARGET = "2025-11-25"

# PersonaVault Core schema versions this adapter is designed to be
# compatible with, once functional tools are added. Declared here so a
# future version-mismatch check has somewhere to read from; nothing in
# Slice 1 checks this against a live PersonaVault installation.
COMPATIBLE_PERSONAVAULT_SCHEMA_VERSIONS = {
    "session_return": "session_return.v0.1",
    "session_intake": "session_intake.v0.1",
}


def server_info() -> dict:
    """Non-functional identity payload. Not a registered MCP tool — a
    future transport slice may expose this via the standard MCP
    initialize/handshake metadata, not as a callable tool."""
    return {
        "adapter_name": ADAPTER_NAME,
        "adapter_version": ADAPTER_VERSION,
        "mcp_protocol_version_target": MCP_PROTOCOL_VERSION_TARGET,
        "compatible_personavault_schema_versions": dict(
            COMPATIBLE_PERSONAVAULT_SCHEMA_VERSIONS
        ),
    }
