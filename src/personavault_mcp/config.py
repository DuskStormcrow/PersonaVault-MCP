"""Adapter configuration.

vault_root/personavault_source_path never touch PersonaVault or the
filesystem themselves -- they're just paths, resolved elsewhere. As of
Slice 5, bind_host/bind_port are real: a Streamable HTTP transport
(server.py) uses them, guarded by assert_bind_policy_is_safe below.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Slice 5 policy: the only bind hosts this adapter will ever start on
# without a further, deliberately separate authorization. IPv4 loopback
# is the documented default; IPv6 loopback and the "localhost" hostname
# (which resolves to one of the two on essentially every real system)
# are accepted for compatibility, not preferred. Nothing else -- in
# particular, never "0.0.0.0" or any real network interface address.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class NonLoopbackBindError(ValueError):
    """Raised by assert_bind_policy_is_safe when bind_host is not a
    recognized loopback address. Slice 5 policy (deliberately, not by
    omission): reject startup entirely rather than permit
    unauthenticated non-loopback operation, or silently coerce the
    value to something safe. A future slice may add an explicit,
    separately-authorized non-loopback + token-auth mode; this one does
    not."""


def assert_bind_policy_is_safe(config: "AdapterConfig") -> None:
    if config.bind_host not in LOOPBACK_HOSTS:
        raise NonLoopbackBindError(
            f"Refusing to start: bind_host {config.bind_host!r} is not a "
            f"recognized loopback address ({sorted(LOOPBACK_HOSTS)}). "
            "Non-loopback binding is not supported in this slice."
        )


@dataclass(frozen=True)
class AdapterConfig:
    """Where the adapter would look for things, once it looks for anything.

    vault_root: path to a PersonaVault Library root. Mirrors the existing
        ``--vault-root`` pattern PersonaVault's own CLI already supports.
        None until a real vault is configured — Slice 1 never resolves or
        reads this path.
    bind_host: defaults to loopback-only, and (Slice 5)
        assert_bind_policy_is_safe() enforces that it stays that way at
        server startup — see LOOPBACK_HOSTS above. Binding wider requires
        a separate, explicit, not-yet-added authorization; this default
        must never silently become "0.0.0.0".
    bind_port: the Streamable HTTP server's local port (Slice 5).
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
