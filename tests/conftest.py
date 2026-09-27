"""Shared test fixtures for Slice 2.

These fixtures exercise real PersonaVault Core (via the same path-bridge
mechanism the adapter itself uses) to build throwaway, per-test vault
fixtures under pytest's tmp_path -- never a checked-in demo persona, and
never the same thing as the polished, committed synthetic fixture a
future demo-packaging slice will add. Nothing here is written to
PersonaVault Core; it is only ever read from and imported.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from personavault_mcp.config import AdapterConfig
from personavault_mcp.personavault_bridge import ensure_personavault_importable

PERSONAVAULT_SOURCE_PATH = Path("/home/user/personavault")


@pytest.fixture(scope="session", autouse=True)
def _personavault_importable():
    ensure_personavault_importable(PERSONAVAULT_SOURCE_PATH)


@pytest.fixture
def vault_factory(tmp_path):
    """Returns a callable that builds a real, initialized PersonaVault
    Vault rooted at a fresh tmp_path, plus a matching AdapterConfig."""
    from personavault.storage import Vault

    def _make() -> tuple["Vault", AdapterConfig]:
        vault_root = tmp_path / "vault"
        vault = Vault(vault_root)
        vault.initialize()
        config = AdapterConfig(
            vault_root=vault_root,
            personavault_source_path=PERSONAVAULT_SOURCE_PATH,
        )
        return vault, config

    return _make


@pytest.fixture
def vault_with_persona(vault_factory):
    """A vault with one freshly created active persona, no approved
    continuity yet. Returns (vault, config, persona_folder_name)."""
    from personavault.models import PersonaDraft

    vault, config = vault_factory()
    package = vault.create_persona(PersonaDraft(name="Test Resident"))
    return vault, config, package.path.name


def commit_approved_memory(vault, persona_folder_name: str, text: str, *, reviewer: str = "test-reviewer") -> None:
    """Drives the real, existing Session Return flow to land one approved
    `approved_memory` continuity event -- the only way this test suite
    populates approved continuity, deliberately, since it is the same
    path a human's own PersonaVault review already uses."""
    session = vault.create_returned_session(
        persona_folder_name,
        host_platform="test-harness",
        summary="test fixture session",
    )
    intake = vault.save_session_intake(
        persona_folder_name,
        session["session_id"],
        candidates=[{"category": "memory", "decision": "approve", "text": text}],
        reviewer=reviewer,
    )
    vault.commit_session_intake(persona_folder_name, intake["intake_id"], reviewer=reviewer)


def hash_vault_tree(vault_root: Path) -> str:
    """A content+structure hash of an entire vault directory tree, used
    to prove a read-only operation left PersonaVault's on-disk state
    byte-for-byte unchanged."""
    digest = hashlib.sha256()
    for path in sorted(vault_root.rglob("*")):
        relative = path.relative_to(vault_root).as_posix()
        digest.update(relative.encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()
