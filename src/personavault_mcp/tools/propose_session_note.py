"""``propose_session_note``: the adapter's second functional MCP tool
(Slice 3), and its first write-adjacent one.

Lets a host say "I learned something that may matter later" by wrapping
PersonaVault's existing, human-reviewed Session Return intake path --
``Vault.create_returned_session(...)`` followed by
``Vault.save_session_intake(...)`` -- and nothing past that.
``Vault.commit_session_intake`` is never imported, never called, and
never reachable from this module. No input field can produce an
"approve" decision; every candidate this tool creates lands with
PersonaVault's own default review decision (``defer``, or natively
``session_only`` when the category itself is ``session_only_note`` --
preserved as PersonaVault's own behavior, not reimplemented here).

Why one intake per proposal, not one accumulating intake
----------------------------------------------------------
The Architecture Contract originally suggested multiple proposals from
one host conversation should land as candidates "within that same
returned session/intake." Verified against the real code
(``Vault._write_intake_record``): saving an intake **overwrites** its
JSON file wholesale; there is no public method to read back an existing
intake's current candidates and append to them (the read side,
``Vault._load_intake_record``, is private). Calling
``save_session_intake`` twice with the same ``intake_id`` but only the
new candidate would silently discard whatever was previously proposed
and not yet reviewed -- a real data-loss risk, not a hypothetical one.

The safe design used here instead: one host conversation maps to one
PersonaVault **session** (``session_id``, created once, reused across
proposals via ``session_correlation.SessionCorrelationCache``), and each
individual proposal call creates its **own new intake** (a fresh,
PersonaVault-generated ``intake_id``) holding exactly one candidate, all
sharing that session_id. Nothing in PersonaVault's schema requires a 1:1
session:intake relationship -- a session can legitimately have many
intakes, each independently reviewable. This is not a workaround; it is
the one mapping the real public API supports without risking data loss
or reaching into private methods.

Provenance (Slice 4)
---------------------
As of the PersonaVault Core Maintenance Gate
(commit d8b9762cf3371572383b72336cd1ad23f91f8dea), ``create_returned_session``
accepts real ``host_conversation_id`` and ``source`` parameters instead
of silently dropping the former and hardcoding the latter. This tool now
passes both, so the session record durably identifies which host, which
host conversation, and that it came via MCP rather than manual desktop
entry -- all readable back from PersonaVault itself, surviving an
adapter restart, with no adapter-side cache required to reconstruct it.

What still does NOT survive an adapter restart: the *correlation*
between a host conversation and its session_id (`session_correlation.py`).
Verified directly against the real Core (grepped every public method on
``Vault``): there is no public method to list or search returned
sessions by persona, host, or host_conversation_id -- only
``create_returned_session`` (write), ``save_session_intake`` (write,
requires an already-known session_id), ``commit_session_intake``
(write), and ``correct_session_intake_candidate`` (write). The read
side (``Vault._load_session_record``) is private. Rediscovering "was
there already an open session for this host conversation" without the
adapter's own in-memory cache would require either a new public Core
query method (not added in this slice -- see the Slice 4 report) or
reaching into a private method (explicitly against this project's own
rule). So: the correlation cache remains for this slice, by verified
necessity, not preference. A repeated host conversation after an
adapter restart opens a second, independent PersonaVault session rather
than continuing the first -- a known adapter limitation, not data loss:
every prior session and its proposals remain fully intact and durably
provenanced on disk, just not automatically re-linked to a
newly-restarted adapter process.
"""

from __future__ import annotations

from typing import Any

from ..config import AdapterConfig
from ..persona_name_guard import UnsafePersonaNameError, assert_persona_name_is_safe
from ..personavault_bridge import (
    PersonaVaultSourceNotFoundError,
    ensure_personavault_importable,
    import_vault_class,
)
from ..schema_guard import assert_schema_is_safe
from ..session_correlation import SessionCorrelationCache

TOOL_NAME = "propose_session_note"

# The value stored in PersonaVault's own `source` field (session_return.v0.1)
# for every session this tool creates -- distinguishing MCP-originated
# sessions from PersonaVault's own default, "manual_user_entry", which
# stays the default for every other caller (the desktop UI, scripts,
# etc.). Host-neutral by construction: it names the protocol (MCP), not
# any specific host or vendor. Checked against every other "source"-like
# value already in personavault/storage.py (created_by/source across
# retirement, corelog, and portrait-library code) -- none of those are
# this exact field's own precedent, which before this slice had exactly
# one value ("manual_user_entry"); "mcp_proposal" matches that value's
# own snake_case, single-token shape.
MCP_SESSION_SOURCE = "mcp_proposal"

# Verified verbatim against personavault/storage.py's own
# SESSION_CANDIDATE_CATEGORIES (commit f9712aceda1912c6e5913bb4b29fc28ed4408933)
# -- not a parallel enum invented here. See
# tests/test_propose_session_note.py::test_candidate_categories_match_personavault_source
# for the automated cross-check that would catch drift.
CANDIDATE_CATEGORIES: tuple[str, ...] = (
    "memory",
    "project_update",
    "relationship_development",
    "development_signal",
    "recognition_fidelity_note",
    "session_only_note",
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "persona": {"type": "string", "minLength": 1},
        "host_id": {"type": "string", "minLength": 1},
        "host_conversation_id": {"type": "string", "minLength": 1},
        "category": {"type": "string", "enum": list(CANDIDATE_CATEGORIES)},
        "text": {"type": "string", "minLength": 1},
        "source_excerpt": {"type": "string"},
    },
    "required": ["persona", "host_id", "host_conversation_id", "category", "text"],
    "additionalProperties": False,
}
# Fails fast at import time if this schema ever drifts unsafe. Also the
# reason a caller-supplied "decision"/"approved"/"commit"/"review_state"/
# "status" field is rejected as malformed input: none of them are in
# `properties`, and additionalProperties is False.
assert_schema_is_safe(INPUT_SCHEMA)

_REQUIRED_FIELDS = ("persona", "host_id", "host_conversation_id", "category", "text")
_OPTIONAL_FIELDS = ("source_excerpt",)
_ALLOWED_FIELDS = set(_REQUIRED_FIELDS) | set(_OPTIONAL_FIELDS)

# Module-level, process-local, non-canonical. See session_correlation.py.
# Not a hidden global in the sense of being unreachable: tests reset it
# explicitly via reset_session_cache_for_tests(), the same pattern
# registry.py already uses for TOOL_REGISTRY.
_SESSION_CACHE = SessionCorrelationCache()


def reset_session_cache_for_tests() -> None:
    """Test-only helper: clears the correlation cache so one test's
    session mapping cannot leak into another's."""
    _SESSION_CACHE.clear()


class ProposeSessionNoteError(Exception):
    """Base class for propose_session_note's own error codes. Every
    subclass carries a fixed, generic message safe to return to a host --
    never a filesystem path, never a raw exception's text, never a stack
    trace."""

    code = "INTERNAL_ADAPTER_ERROR"


class MalformedRequestError(ProposeSessionNoteError):
    code = "MALFORMED_REQUEST"


class PersonaNotFoundError(ProposeSessionNoteError):
    code = "PERSONA_NOT_FOUND"


class VaultUnavailableError(ProposeSessionNoteError):
    code = "VAULT_UNAVAILABLE"


class SessionCreateFailureError(ProposeSessionNoteError):
    code = "SESSION_CREATE_FAILURE"


class IntakeSaveFailureError(ProposeSessionNoteError):
    code = "INTAKE_SAVE_FAILURE"


class DuplicateProposalError(ProposeSessionNoteError):
    """Reserved for interface completeness. Verified unreachable in this
    slice: PersonaVault's own duplicate protection
    (Vault._committed_candidate_keys) operates only at
    commit_session_intake time, scoped to (event_type, intake_id,
    candidate_id) -- and this tool never calls commit_session_intake,
    and always creates a fresh intake_id per proposal. There is
    therefore no native mechanism that would ever raise this in Slice 3;
    do not invent one (a separate dedup database is explicitly out of
    scope). Repeated identical proposals create independent, separately
    reviewable pending candidates -- see
    tests/test_propose_session_note.py for the verified behavior."""

    code = "DUPLICATE_PROPOSAL"


class StorageFailureError(ProposeSessionNoteError):
    code = "STORAGE_FAILURE"


class InternalAdapterError(ProposeSessionNoteError):
    code = "INTERNAL_ADAPTER_ERROR"


def _validate_input(raw_input: Any) -> dict[str, str]:
    if not isinstance(raw_input, dict):
        raise MalformedRequestError("Input must be a JSON object.")

    extra_keys = set(raw_input) - _ALLOWED_FIELDS
    if extra_keys:
        raise MalformedRequestError(f"Unknown field(s): {sorted(extra_keys)}")

    for field in _REQUIRED_FIELDS:
        value = raw_input.get(field)
        if not isinstance(value, str) or not value.strip():
            raise MalformedRequestError(f"'{field}' is required and must be a non-empty string.")

    try:
        assert_persona_name_is_safe(raw_input["persona"])
    except UnsafePersonaNameError as exc:
        raise MalformedRequestError(str(exc)) from exc

    category = raw_input["category"]
    if category not in CANDIDATE_CATEGORIES:
        raise MalformedRequestError(f"Unsupported category: {category!r}")

    source_excerpt = raw_input.get("source_excerpt")
    if source_excerpt is not None and not isinstance(source_excerpt, str):
        raise MalformedRequestError("'source_excerpt' must be a string.")

    parsed = {field: raw_input[field] for field in _REQUIRED_FIELDS}
    if source_excerpt:
        parsed["source_excerpt"] = source_excerpt
    return parsed


def _resolve_vault(config: AdapterConfig):
    if config.personavault_source_path is None:
        raise VaultUnavailableError("PersonaVault source is not configured.")
    if config.vault_root is None:
        raise VaultUnavailableError("PersonaVault Library root is not configured.")

    try:
        ensure_personavault_importable(config.personavault_source_path)
        vault_class = import_vault_class()
    except PersonaVaultSourceNotFoundError as exc:
        raise VaultUnavailableError("PersonaVault source is not configured correctly.") from exc

    if not config.vault_root.is_dir():
        raise VaultUnavailableError("Configured PersonaVault Library root does not exist.")
    if not (config.vault_root / "Active").is_dir():
        raise VaultUnavailableError(
            "Configured PersonaVault Library root does not look like an initialized vault."
        )

    return vault_class(config.vault_root)


def _get_or_create_session(vault, persona: str, host_id: str, host_conversation_id: str) -> str:
    cached = _SESSION_CACHE.get(persona, host_id, host_conversation_id)
    if cached is not None:
        return cached

    try:
        session = vault.create_returned_session(
            persona,
            host_platform=host_id,
            host_conversation_id=host_conversation_id,
            source=MCP_SESSION_SOURCE,
            summary="Session opened by an MCP host proposal.",
        )
    except FileNotFoundError as exc:
        raise PersonaNotFoundError("No active persona matches the given name.") from exc
    except ValueError as exc:
        # Persona resolved but something about its data was malformed --
        # distinct from "not found." Not expected to be reachable given
        # this tool always passes status="active" itself (never a
        # host-supplied value), but PersonaVault's own validation could
        # still raise for a corrupted record.
        raise SessionCreateFailureError("A returned session could not be created.") from exc
    except OSError as exc:
        raise SessionCreateFailureError("A storage error occurred while opening a session.") from exc

    session_id = session["session_id"]
    _SESSION_CACHE.put(persona, host_id, host_conversation_id, session_id)
    return session_id


def handle(raw_input: Any, *, config: AdapterConfig) -> dict[str, Any]:
    """Entry point the tool registry calls.

    Returns the bounded output dict only once the proposal is durably
    saved as a pending PersonaVault intake. Raises a
    ``ProposeSessionNoteError`` subclass on any failure before that point
    -- success is never returned for a partially completed operation.
    """
    parsed = _validate_input(raw_input)
    vault = _resolve_vault(config)

    session_id = _get_or_create_session(
        vault, parsed["persona"], parsed["host_id"], parsed["host_conversation_id"]
    )

    candidate: dict[str, Any] = {
        "category": parsed["category"],
        "text": parsed["text"],
    }
    if "source_excerpt" in parsed:
        candidate["source_excerpt"] = parsed["source_excerpt"]
    # Deliberately no "decision" key: save_session_intake defaults an
    # omitted decision to "defer" (or PersonaVault forces "session_only"
    # itself when category == "session_only_note"). There is no schema
    # path by which a host-supplied value could reach this dict at all.

    try:
        intake = vault.save_session_intake(
            parsed["persona"],
            session_id,
            candidates=[candidate],
            reviewer="",
        )
    except ValueError as exc:
        raise IntakeSaveFailureError("The proposal could not be saved for review.") from exc
    except OSError as exc:
        raise IntakeSaveFailureError("A storage error occurred while saving the proposal.") from exc
    except Exception as exc:  # noqa: BLE001 - last-resort containment
        raise InternalAdapterError("An unexpected adapter error occurred.") from exc

    saved_candidate = intake["candidates"][0]

    return {
        "session_id": session_id,
        "intake_id": intake["intake_id"],
        "candidate_id": saved_candidate["candidate_id"],
        "status": "pending_human_review",
        # Reflects PersonaVault's own actual decision for this candidate
        # -- "defer" for five of six categories, natively "session_only"
        # for session_only_note. Never "approve" or "reject": nothing in
        # this tool's input schema or call path can produce either.
        "review_state": saved_candidate["decision"],
        "message": (
            "This has been recorded for human review inside PersonaVault. "
            "It is not yet part of approved continuity."
        ),
    }
