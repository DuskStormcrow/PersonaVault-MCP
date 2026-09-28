"""Reproducible builder for PersonaVault-MCP's synthetic demo vault.

    python -m personavault_mcp.demo.build_demo_vault
    python -m personavault_mcp.demo.build_demo_vault --reset

Creates (if not already present) one completely fictional PersonaVault
resident -- ``Rook``, see ``fixture.py`` -- and a small, already-approved
continuity history, in an isolated vault at ``demo/vault`` under this
repository's root by default. Never touches, infers, or requires a real
PersonaVault Library; see ``safety.py`` for the guard rails that enforce
this even under an explicit ``--vault-root`` override.

Safe to re-run: an existing demo resident and its already-seeded
continuity are left exactly as they are, never duplicated. Pass
``--reset`` to delete and rebuild the demo vault from scratch --
destructive, but confined strictly to a directory this tool itself
marked as a demo vault (again, see ``safety.py``).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

from .. import personavault_bridge
from ..config import AdapterConfig
from .fixture import (
    APPROVED_CONTINUITY_SEED,
    DEMO_PERSONA_NAME,
    DEMO_RECIPE_ID,
    DEMO_SEED_HOST_PLATFORM,
    DEMO_SEED_REVIEWER,
    DEMO_SEED_SOURCE,
)
from .safety import assert_marked_demo_directory, assert_safe_demo_target, write_demo_marker

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DEMO_VAULT_ROOT = REPO_ROOT / "demo" / "vault"


def _default_personavault_source_path() -> Path:
    configured = AdapterConfig.from_env().personavault_source_path
    if configured is not None:
        return configured
    # Test-environment convenience matching this repo's existing
    # convention (tests/conftest.py, scripts/smoke_test.py) -- not a
    # hardcoded production path. A real caller should have
    # PERSONAVAULT_MCP_SOURCE_PATH set (or pass --personavault-source-path).
    return Path("/home/user/personavault")


def _build_persona_draft() -> Any:
    from personavault import guided_creation
    from personavault.models import PersonaDraft

    card = guided_creation.locked_persona_card(
        guided_creation.generate_persona_card(name=DEMO_PERSONA_NAME, recipe_id=DEMO_RECIPE_ID)
    )
    fields = guided_creation.manifest_foundation_fields(card)
    return PersonaDraft(
        name=DEMO_PERSONA_NAME,
        persona_card=card,
        # PersonaDraft's own dataclass defaults for these two fields are
        # PersonaVault Core's real, hardcoded owner identity
        # (personavault.constants.DEFAULT_USER_HANDLE / _REAL_NAME) --
        # correct for a real persona created by its one real owner, but
        # exactly the kind of real, identifying data this public-demo
        # fixture must never carry. Overridden here with an obviously
        # generic placeholder; not a PersonaVault Core change.
        relationship_user_name="Guest",
        relationship_real_name="",
        **fields,
    )


def _seed_continuity(vault: Any, persona_folder: str) -> int:
    """Idempotent: only seeds if this resident does not already have at
    least as many approved continuity events as the fixture defines.
    Never re-opens a session or re-saves an intake once that's true, so
    a rerun cannot create duplicate corelog entries."""
    existing = vault.approved_continuity_events(persona_folder)
    if len(existing) >= len(APPROVED_CONTINUITY_SEED):
        return 0

    session = vault.create_returned_session(
        persona_folder,
        host_platform=DEMO_SEED_HOST_PLATFORM,
        source=DEMO_SEED_SOURCE,
        summary="Synthetic history seeded by the PersonaVault-MCP demo fixture builder.",
    )
    intake = vault.save_session_intake(
        persona_folder,
        session["session_id"],
        candidates=[
            {"category": item["category"], "decision": "approve", "text": item["text"]}
            for item in APPROVED_CONTINUITY_SEED
        ],
        reviewer=DEMO_SEED_REVIEWER,
    )
    result = vault.commit_session_intake(
        persona_folder, intake["intake_id"], reviewer=DEMO_SEED_REVIEWER
    )
    return result["counts"]["approved"]


def build(vault_root: Path, personavault_source_path: Path) -> dict[str, Any]:
    """Builds (or, if it already exists, verifies/completes) the demo
    vault at ``vault_root``. Safe to call repeatedly."""
    assert_safe_demo_target(vault_root)

    personavault_bridge.ensure_personavault_importable(personavault_source_path)
    from personavault.storage import Vault

    vault_root.mkdir(parents=True, exist_ok=True)
    write_demo_marker(vault_root)

    vault = Vault(vault_root)
    vault.initialize()

    existing = [
        package
        for package in vault.list_personas("active")
        if package.manifest.get("name") == DEMO_PERSONA_NAME
    ]
    if existing:
        persona_folder = existing[0].path.name
        persona_created = False
    else:
        package = vault.create_persona(_build_persona_draft())
        persona_folder = package.path.name
        persona_created = True

    continuity_appended = _seed_continuity(vault, persona_folder)

    return {
        "vault_root": vault_root,
        "persona_folder": persona_folder,
        "persona_created": persona_created,
        "continuity_events_appended": continuity_appended,
    }


def reset(vault_root: Path) -> None:
    """Deletes ``vault_root`` entirely. Refuses unless it matches the
    real-vault-overlap check AND carries this tool's own marker file
    (or does not exist at all, in which case this is a clean no-op)."""
    assert_safe_demo_target(vault_root)
    assert_marked_demo_directory(vault_root)
    if vault_root.exists():
        shutil.rmtree(vault_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vault-root",
        type=Path,
        default=DEFAULT_DEMO_VAULT_ROOT,
        help=f"Where to build the demo vault (default: {DEFAULT_DEMO_VAULT_ROOT}).",
    )
    parser.add_argument(
        "--personavault-source-path",
        type=Path,
        default=None,
        help="PersonaVault Core checkout to import (default: PERSONAVAULT_MCP_SOURCE_PATH, "
        "or a test-environment fallback).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the demo vault before rebuilding it. Confined strictly to a "
        "directory this tool itself marked as a demo vault.",
    )
    args = parser.parse_args(argv)
    source_path = args.personavault_source_path or _default_personavault_source_path()

    try:
        if args.reset:
            reset(args.vault_root)
            print(f"Reset: removed {args.vault_root}")
        result = build(args.vault_root, source_path)
    except Exception as exc:  # noqa: BLE001 - CLI top level: report and exit non-zero
        print(f"Demo vault build failed: {exc}", file=sys.stderr)
        return 1

    print(f"Demo vault ready at: {result['vault_root']}")
    print(f"Synthetic resident folder: {result['persona_folder']!r}")
    print(
        "Created new synthetic resident."
        if result["persona_created"]
        else "Synthetic resident already existed; left unchanged."
    )
    print(f"Approved continuity events appended this run: {result['continuity_events_appended']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
