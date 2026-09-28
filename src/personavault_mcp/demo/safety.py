"""Guard rails keeping the demo builder away from any real PersonaVault
Library, ever -- including under an explicit path override.

Two independent checks, deliberately layered (defense in depth):

- ``assert_safe_demo_target``: refuses a path that matches or overlaps
  the real vault root this environment is actually configured for
  (``PERSONAVAULT_MCP_VAULT_ROOT``). Never scans the filesystem or
  guesses where a real vault might be -- only compares against a value
  an operator explicitly configured, exactly the same source
  ``AdapterConfig.from_env()`` itself reads.
- ``assert_marked_demo_directory``: refuses a *destructive* reset
  against any directory that does not carry this builder's own marker
  file -- so even if no real vault root happens to be configured in a
  given environment (the first check would then have nothing to compare
  against), a reset still cannot land on an arbitrary or pre-existing
  directory that this tool did not itself create.
"""

from __future__ import annotations

from pathlib import Path

from ..config import AdapterConfig

DEMO_MARKER_FILENAME = ".personavault_demo_marker"


class UnsafeDemoTargetError(ValueError):
    """Raised when a path is not safe for the demo builder to create,
    rebuild, or delete."""


def assert_safe_demo_target(path: Path) -> None:
    resolved = path.resolve()
    real_root_value = AdapterConfig.from_env().vault_root
    if real_root_value is None:
        return
    real_root = Path(real_root_value).resolve()
    if resolved == real_root or resolved in real_root.parents or real_root in resolved.parents:
        raise UnsafeDemoTargetError(
            f"Refusing to use {path} as a demo vault path: it matches or "
            "overlaps the real PersonaVault Library root this environment "
            "is configured for (PERSONAVAULT_MCP_VAULT_ROOT). The demo "
            "builder never targets that path, under any flag."
        )


def assert_marked_demo_directory(path: Path) -> None:
    if not path.exists():
        return
    marker = path / DEMO_MARKER_FILENAME
    if not marker.is_file():
        raise UnsafeDemoTargetError(
            f"Refusing to reset {path}: it exists but does not carry this "
            f"builder's own marker file ({DEMO_MARKER_FILENAME}), so it "
            "does not look like a demo vault this tool created. Destructive "
            "reset is confined strictly to directories this tool marked "
            "itself."
        )


def write_demo_marker(vault_root: Path) -> None:
    marker = vault_root / DEMO_MARKER_FILENAME
    marker.write_text(
        "This directory is a disposable PersonaVault-MCP demo vault.\n"
        "It was created by personavault_mcp.demo.build_demo_vault and "
        "contains no real PersonaVault resident data.\n"
        "Safe to delete; rerun the builder (optionally with --reset) to "
        "recreate it.\n",
        encoding="utf-8",
    )
