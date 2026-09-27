"""Adapter configuration skeleton.

Nothing in this module talks to PersonaVault or opens a network socket.
It only defines the shape configuration will take, with safe,
localhost-first defaults, so later slices wire real behavior into an
already-reviewed shape rather than inventing config as they go.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AdapterConfig:
    """Where the adapter would look for things, once it looks for anything.

    vault_root: path to a PersonaVault Library root. Mirrors the existing
        ``--vault-root`` pattern PersonaVault's own CLI already supports.
        None until a real vault is configured — Slice 1 never resolves or
        reads this path.
    bind_host: defaults to loopback-only. Binding wider is a separate,
        explicit opt-in a later slice must add deliberately — this default
        must never silently become "0.0.0.0".
    bind_port: placeholder; unused until a real transport exists.
    auth_token_env_var: the *name* of an environment variable the adapter
        would read a token from — never a token value itself, and never a
        path inside a PersonaVault Library.
    """

    vault_root: Path | None = None
    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    auth_token_env_var: str = "PERSONAVAULT_MCP_AUTH_TOKEN"

    # Deliberately distinct from vault_root: this is where PersonaVault's
    # *source code* (a checkout of the PersonaVault repo) lives, so it can
    # be added to sys.path (see personavault_bridge.py). vault_root is
    # where a persona *Library's data* (Active/Archive/Exports/AppConfig)
    # lives. Confusing the two would mean pointing the importable-package
    # lookup at someone's persona data, or vice versa.
    personavault_source_path: Path | None = None

    @classmethod
    def from_env(cls) -> "AdapterConfig":
        """Read config from environment variables only. No file parsing,
        no PersonaVault access, no network calls — safe to call at import
        time or in a test."""
        vault_root_str = os.environ.get("PERSONAVAULT_MCP_VAULT_ROOT")
        source_path_str = os.environ.get("PERSONAVAULT_MCP_SOURCE_PATH")
        return cls(
            vault_root=Path(vault_root_str) if vault_root_str else None,
            bind_host=os.environ.get("PERSONAVAULT_MCP_BIND_HOST", "127.0.0.1"),
            bind_port=int(os.environ.get("PERSONAVAULT_MCP_BIND_PORT", "8765")),
            personavault_source_path=Path(source_path_str) if source_path_str else None,
        )
