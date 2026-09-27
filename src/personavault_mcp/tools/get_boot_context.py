"""``get_boot_context``: the adapter's one functional MCP tool in Slice 2.

Wraps ``Vault.boot_package_preview(name_or_folder, status="active")`` and
projects its result down to an explicit allowlist of fields. The full
``boot_package_preview()`` dict is never passed through or returned
as-is -- only the fields named in ``ALLOWED_OUTPUT_FIELDS`` ever leave
this module.

This tool is read-only. It never calls any PersonaVault method other
than ``load_persona`` (used only to distinguish "not found" from
"found but incomplete" without inspecting exception text that may
contain a filesystem path) and ``boot_package_preview`` itself.
"""

from __future__ import annotations

from typing import Any

from ..config import AdapterConfig
from ..personavault_bridge import (
    PersonaVaultSourceNotFoundError,
    ensure_personavault_importable,
    import_vault_class,
)
from ..schema_guard import assert_schema_is_safe

TOOL_NAME = "get_boot_context"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "persona": {"type": "string", "minLength": 1},
    },
    "required": ["persona"],
    "additionalProperties": False,
}
# Fails fast at import time if this schema ever drifts unsafe.
assert_schema_is_safe(INPUT_SCHEMA)

# The explicit allowlist -- the ONLY boot_package_preview() keys this
# tool is permitted to read and re-expose. Anything boot_package_preview()
# returns that is not in this tuple is private by default: allowlist,
# never denylist.
ALLOWED_OUTPUT_FIELDS: tuple[str, ...] = (
    "persona_name",
    "persona_id",
    "schema_version",
    "memory_behavior",
    "doctrine",
    "host_boundary",
    "boot_prompt",
    "memory_rules",
    "approved_continuity",
    "approved_continuity_limit",
)

# Fields boot_package_preview() is known to also return, which this tool
# must NEVER expose. Verified directly against personavault/storage.py
# (commit f9712aceda1912c6e5913bb4b29fc28ed4408933): all ten allowed
# field names above match the real return dict's keys exactly, with no
# renaming needed. This tuple exists only as a documented cross-check,
# not as the enforcement mechanism -- the allowlist above is what
# actually decides what leaves this module.
KNOWN_PRIVATE_SOURCE_FIELDS: tuple[str, ...] = (
    "corelog_status",
    "asset_status",
    "checksum_status",
    "state_status",
    "origin",
    "preview_text",
)


class BootContextError(Exception):
    """Base class for get_boot_context's own error codes. Every subclass
    carries a fixed, generic message safe to return to a host -- never a
    filesystem path, never a raw exception's text, never a stack trace."""

    code = "INTERNAL_ADAPTER_ERROR"


class MalformedRequestError(BootContextError):
    code = "MALFORMED_REQUEST"


class PersonaNotFoundError(BootContextError):
    code = "PERSONA_NOT_FOUND"


class VaultUnavailableError(BootContextError):
    code = "VAULT_UNAVAILABLE"


class PersonaFilesIncompleteError(BootContextError):
    code = "PERSONA_FILES_INCOMPLETE"


class StorageFailureError(BootContextError):
    code = "STORAGE_FAILURE"


class InternalAdapterError(BootContextError):
    code = "INTERNAL_ADAPTER_ERROR"


def _validate_input(raw_input: Any) -> str:
    if not isinstance(raw_input, dict):
        raise MalformedRequestError("Input must be a JSON object.")
    allowed_keys = {"persona"}
    extra_keys = set(raw_input) - allowed_keys
    if extra_keys:
        raise MalformedRequestError(f"Unknown field(s): {sorted(extra_keys)}")
    persona = raw_input.get("persona")
    if not isinstance(persona, str) or not persona.strip():
        raise MalformedRequestError("'persona' is required and must be a non-empty string.")
    return persona


def _resolve_vault(config: AdapterConfig):
    if config.personavault_source_path is None:
        raise VaultUnavailableError("PersonaVault source is not configured.")
    if config.vault_root is None:
        raise VaultUnavailableError("PersonaVault Library root is not configured.")

    try:
        ensure_personavault_importable(config.personavault_source_path)
        vault_class = import_vault_class()
    except PersonaVaultSourceNotFoundError as exc:
        # Deliberately do not include str(exc) -- it names a filesystem
        # path.
        raise VaultUnavailableError("PersonaVault source is not configured correctly.") from exc

    if not config.vault_root.is_dir():
        raise VaultUnavailableError("Configured PersonaVault Library root does not exist.")
    if not (config.vault_root / "Active").is_dir():
        raise VaultUnavailableError(
            "Configured PersonaVault Library root does not look like an initialized vault."
        )

    return vault_class(config.vault_root)


def handle(raw_input: Any, *, config: AdapterConfig) -> dict[str, Any]:
    """Entry point the tool registry calls.

    Returns the bounded output dict on success. Raises a
    ``BootContextError`` subclass on failure; every subclass's message is
    a fixed, generic string safe to return to a host as-is.
    """
    persona = _validate_input(raw_input)
    vault = _resolve_vault(config)

    # Two sequential calls, deliberately: load_persona() alone first, to
    # distinguish "this persona cannot be resolved at all" from "it
    # resolves but boot_package_preview() then fails reading its files" --
    # without ever inspecting either exception's message text, which may
    # contain a filesystem path (Python's own FileNotFoundError messages
    # embed the path they were reading). Both calls raise the same
    # FileNotFoundError type in PersonaVault Core, so message inspection
    # would be the only alternative and is exactly what must be avoided.
    try:
        vault.load_persona(persona, status="active")
    except FileNotFoundError as exc:
        raise PersonaNotFoundError("No active persona matches the given name.") from exc
    except OSError as exc:
        raise StorageFailureError("A storage error occurred while resolving this persona.") from exc

    try:
        preview = vault.boot_package_preview(persona, status="active")
    except FileNotFoundError as exc:
        raise PersonaFilesIncompleteError(
            "This persona's boot materials are incomplete."
        ) from exc
    except OSError as exc:
        raise StorageFailureError("A storage error occurred while reading this persona.") from exc
    except Exception as exc:  # noqa: BLE001 - last-resort containment, see module docstring
        raise InternalAdapterError("An unexpected adapter error occurred.") from exc

    return _project_output(preview)


def _project_output(preview: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in ALLOWED_OUTPUT_FIELDS if field not in preview]
    if missing:
        # boot_package_preview() no longer returns a field this tool's
        # contract depends on -- fail loudly rather than silently return
        # a thinner object than the contract promises.
        raise StorageFailureError(
            f"PersonaVault's boot preview no longer provides expected data ({len(missing)} field(s))."
        )

    output = {field: preview[field] for field in ALLOWED_OUTPUT_FIELDS}

    # Defense in depth: never expose more approved-continuity events than
    # PersonaVault itself declares as its own limit, whatever that number
    # is. This adapter does not hardcode "5" independently -- if
    # PersonaVault Core's APPROVED_CONTINUITY_PREVIEW_LIMIT constant ever
    # changes, this tool inherits the new limit automatically rather than
    # silently drifting out of sync with Core's own declared contract.
    limit = output["approved_continuity_limit"]
    output["approved_continuity"] = list(output["approved_continuity"])[:limit]

    return output
