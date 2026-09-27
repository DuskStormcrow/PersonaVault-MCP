"""Slice 2 tests for get_boot_context: the tool's behavior, its output
allowlist, its error mapping, and its read-only/side-effect-free nature
against a real (throwaway, tmp_path) PersonaVault vault.
"""

from __future__ import annotations

import pytest

from .conftest import commit_approved_memory, hash_vault_tree
from personavault_mcp.tools import get_boot_context
from personavault_mcp.tools.get_boot_context import (
    ALLOWED_OUTPUT_FIELDS,
    KNOWN_PRIVATE_SOURCE_FIELDS,
    MalformedRequestError,
    PersonaFilesIncompleteError,
    PersonaNotFoundError,
    StorageFailureError,
    VaultUnavailableError,
    handle,
)


# --- 1 & 2: output allowlist -------------------------------------------------

def test_returns_only_allowed_fields(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    result = handle({"persona": persona}, config=config)
    assert set(result.keys()) == set(ALLOWED_OUTPUT_FIELDS)


def test_known_private_fields_never_leak_through(vault_with_persona) -> None:
    """boot_package_preview() itself returns these fields internally
    (verified directly against personavault/storage.py); this proves the
    adapter's projection drops them rather than merely happening not to
    include them by omission."""
    vault, config, persona = vault_with_persona
    result = handle({"persona": persona}, config=config)
    for private_field in KNOWN_PRIVATE_SOURCE_FIELDS:
        assert private_field not in result

    # Cross-check against the real underlying call, to prove those
    # fields do genuinely exist on the source side and are being
    # deliberately filtered, not coincidentally absent.
    raw = vault.boot_package_preview(persona, status="active")
    for private_field in KNOWN_PRIVATE_SOURCE_FIELDS:
        assert private_field in raw


# --- 3: approved continuity never exceeds the contract limit ----------------

def test_approved_continuity_never_exceeds_declared_limit(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    limit_probe = handle({"persona": persona}, config=config)["approved_continuity_limit"]

    # Commit more approved events than the declared limit and confirm the
    # tool still truncates to it -- proves enforcement, not coincidence.
    for i in range(limit_probe + 2):
        commit_approved_memory(vault, persona, text=f"Memory number {i}")

    result = handle({"persona": persona}, config=config)
    assert len(result["approved_continuity"]) <= result["approved_continuity_limit"]
    assert result["approved_continuity_limit"] == limit_probe


# --- 4: empty approved continuity is a successful result --------------------

def test_empty_approved_continuity_is_success_not_error(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    result = handle({"persona": persona}, config=config)
    assert result["approved_continuity"] == []
    assert result["persona_name"]  # a genuine, successful, populated result


# --- 5: unknown persona ------------------------------------------------------

def test_unknown_persona_returns_persona_not_found(vault_factory) -> None:
    _vault, config = vault_factory()
    with pytest.raises(PersonaNotFoundError) as excinfo:
        handle({"persona": "Nobody Here"}, config=config)
    assert excinfo.value.code == "PERSONA_NOT_FOUND"


# --- 6: malformed input -------------------------------------------------------

@pytest.mark.parametrize(
    "raw_input",
    [
        {},
        {"persona": ""},
        {"persona": "   "},
        {"persona": 123},
        {"persona": "Someone", "status": "archive"},
        {"persona": "Someone", "extra": "field"},
        "not-a-dict",
        None,
    ],
)
def test_malformed_input_returns_malformed_request(vault_factory, raw_input) -> None:
    _vault, config = vault_factory()
    with pytest.raises(MalformedRequestError) as excinfo:
        handle(raw_input, config=config)
    assert excinfo.value.code == "MALFORMED_REQUEST"


# --- 7: no filesystem-path alternate input mechanism -------------------------

@pytest.mark.parametrize(
    "path_like_value",
    [
        "../../../etc/passwd",
        "/etc/passwd",
        "..\\..\\Windows\\System32",
        "Active/../../Archive/Someone",
    ],
)
def test_path_like_persona_value_is_treated_as_a_name_not_a_path(vault_factory, path_like_value) -> None:
    """A path-shaped string in the only accepted field ('persona') is
    just a name that fails to match -- never a traversal into the
    filesystem."""
    _vault, config = vault_factory()
    with pytest.raises(PersonaNotFoundError):
        handle({"persona": path_like_value}, config=config)


# --- 8 & 9: no raw paths or stack traces in errors ---------------------------

def test_vault_unavailable_error_has_no_path_in_message(tmp_path) -> None:
    from personavault_mcp.config import AdapterConfig

    missing_root = tmp_path / "does-not-exist"
    config = AdapterConfig(
        vault_root=missing_root,
        personavault_source_path=_real_personavault_source(),
    )
    with pytest.raises(VaultUnavailableError) as excinfo:
        handle({"persona": "Anyone"}, config=config)
    message = str(excinfo.value)
    assert str(missing_root) not in message
    assert "Traceback" not in message


def test_persona_not_found_error_message_has_no_path(vault_factory) -> None:
    _vault, config = vault_factory()
    with pytest.raises(PersonaNotFoundError) as excinfo:
        handle({"persona": "Nobody Here"}, config=config)
    message = str(excinfo.value)
    assert str(config.vault_root) not in message
    assert "Traceback" not in message


def test_persona_files_incomplete_error_has_no_path(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    persona_dir = config.vault_root / "Active" / persona
    (persona_dir / "boot_prompt.md").unlink()

    with pytest.raises(PersonaFilesIncompleteError) as excinfo:
        handle({"persona": persona}, config=config)
    message = str(excinfo.value)
    assert str(persona_dir) not in message
    assert "boot_prompt.md" not in message
    assert "Traceback" not in message


def _real_personavault_source():
    from pathlib import Path

    return Path("/home/user/personavault")


# --- 10: archived persona cannot be retrieved --------------------------------

def test_archived_persona_is_not_reachable(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    vault.archive_persona(persona)

    with pytest.raises(PersonaNotFoundError):
        handle({"persona": persona}, config=config)


# --- 11, 12, 13: no mutation, no Corelog append, no Session Return ----------

def test_repeated_calls_leave_vault_byte_for_byte_unchanged(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    before = hash_vault_tree(config.vault_root)

    for _ in range(5):
        handle({"persona": persona}, config=config)

    after = hash_vault_tree(config.vault_root)
    assert before == after, "get_boot_context must never modify PersonaVault's on-disk state."


def test_handler_module_calls_only_load_persona_and_boot_package_preview() -> None:
    """Static confirmation that the handler's PersonaVault call surface
    is exactly what the contract allows -- not commit_session_intake,
    not append_corelog_entry, not create_returned_session, not any
    Session Return method."""
    import inspect

    source = inspect.getsource(get_boot_context)
    forbidden = (
        "commit_session_intake",
        "save_session_intake",
        "create_returned_session",
        "append_corelog_entry",
        "update_persona",
        "append_foundation_amendment",
    )
    for name in forbidden:
        assert name not in source, f"get_boot_context.py must never call {name}."
    assert "load_persona" in source
    assert "boot_package_preview" in source


# --- 14 (registry side, covered in test_bootstrap.py) ------------------------
# --- 15 (Slice 1 tests still passing, covered by running the whole suite) ---
# --- 16 (brand terminology, covered in test_capability_boundary.py) ---------
