"""Slice 3 tests for propose_session_note: input rejection, the
proposal-only review-state guarantee, session/intake mapping, verified
(non-)duplicate behavior, partial-write recoverability, and the
human-commit boundary end to end.
"""

from __future__ import annotations

import inspect
import json
import re

import pytest

from personavault_mcp.session_correlation import SessionCorrelationCache
from personavault_mcp.tools import propose_session_note
from personavault_mcp.tools.get_boot_context import handle as get_boot_context_handle
from personavault_mcp.tools.propose_session_note import (
    CANDIDATE_CATEGORIES,
    DuplicateProposalError,
    IntakeSaveFailureError,
    MalformedRequestError,
    PersonaNotFoundError,
    VaultUnavailableError,
    handle,
    reset_session_cache_for_tests,
)


@pytest.fixture(autouse=True)
def _clean_session_cache():
    reset_session_cache_for_tests()
    yield
    reset_session_cache_for_tests()


def _base_input(**overrides) -> dict:
    base = {
        "persona": overrides.pop("persona", "placeholder"),
        "host_id": "test-host",
        "host_conversation_id": "conversation-1",
        "category": "memory",
        "text": "The user mentioned they adopted a cat named Whiskers.",
    }
    base.update(overrides)
    return base


# --- category canary: real source, not a re-invented enum -------------------

def test_candidate_categories_match_personavault_source() -> None:
    from personavault.storage import SESSION_CANDIDATE_CATEGORIES

    assert CANDIDATE_CATEGORIES == SESSION_CANDIDATE_CATEGORIES


# --- 1-5, 9: forbidden / unknown fields --------------------------------------

@pytest.mark.parametrize(
    "forbidden_extra",
    [
        {"decision": "defer"},
        {"decision": "approve"},
        {"decision": "reject"},
        {"approved": True},
        {"commit": True},
        {"review_state": "approve"},
        {"status": "committed"},
        {"corelog_event_id": "event_deadbeef"},
        {"file_path": "/etc/passwd"},
        {"vault_root": "/some/path"},
        {"anything_unrecognized": "value"},
    ],
)
def test_forbidden_or_unknown_fields_are_rejected(vault_with_persona, forbidden_extra) -> None:
    vault, config, persona = vault_with_persona
    raw_input = _base_input(persona=persona, **forbidden_extra)
    with pytest.raises(MalformedRequestError):
        handle(raw_input, config=config)


def test_decision_approve_specifically_is_rejected(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    with pytest.raises(MalformedRequestError) as excinfo:
        handle(_base_input(persona=persona, decision="approve"), config=config)
    assert excinfo.value.code == "MALFORMED_REQUEST"


def test_decision_reject_specifically_is_rejected(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    with pytest.raises(MalformedRequestError):
        handle(_base_input(persona=persona, decision="reject"), config=config)


# --- 15: malformed category ---------------------------------------------------

def test_malformed_category_is_rejected(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    with pytest.raises(MalformedRequestError):
        handle(_base_input(persona=persona, category="not_a_real_category"), config=config)


# --- 5, 6, 7: static call-surface proof --------------------------------------

_TRIPLE_QUOTED_STRING = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')


def test_handler_module_never_references_commit_or_mutation_methods() -> None:
    """Docstrings are stripped before scanning: this module's own
    prose legitimately names commit_session_intake to explain that it is
    never called -- that sentence is documentation, not a call site."""
    source = _TRIPLE_QUOTED_STRING.sub("", inspect.getsource(propose_session_note))
    forbidden = (
        "commit_session_intake",
        "update_persona",
        "append_foundation_amendment",
        "append_corelog_entry",
        "correct_session_intake_candidate",
        "recall",
        "fts5",
        "sqlite3",
    )
    for name in forbidden:
        assert name not in source, f"propose_session_note.py must never reference {name}."
    assert "create_returned_session" in source
    assert "save_session_intake" in source


def test_module_has_no_networking_or_logging() -> None:
    """No transport was added, and nothing exists that could leak
    proposal text into a log (there is no logging at all)."""
    source = inspect.getsource(propose_session_note)
    forbidden = (
        "socket",
        "aiohttp",
        "fastapi",
        "flask",
        "http.server",
        "logging",
        "print(",
    )
    for token in forbidden:
        assert token not in source, f"propose_session_note.py must not contain {token!r}."


# --- 10: no arbitrary filesystem path input -----------------------------------

@pytest.mark.parametrize(
    "path_like_persona",
    ["../../../etc/passwd", "/etc/passwd", "Active/../../Archive/Someone"],
)
def test_path_like_persona_value_is_rejected_before_reaching_personavault(vault_factory, path_like_persona) -> None:
    """See persona_name_guard.py: this is the fix for a real PersonaVault
    Core issue found while implementing this slice
    (Vault._resolve_persona_dir's absolute-path join bypass), verified
    directly -- without this guard, persona="/etc/passwd" reached
    create_returned_session and raised an uncaught NotADirectoryError
    from inside PersonaVault Core itself."""
    _vault, config = vault_factory()
    with pytest.raises(MalformedRequestError):
        handle(_base_input(persona=path_like_persona), config=config)


# --- 11, 12, 13: proposal stays pending; human commit is the only path ------

def test_proposal_remains_pending_before_human_review(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    result = handle(_base_input(persona=persona), config=config)

    assert result["status"] == "pending_human_review"
    assert result["review_state"] == "defer"
    assert "not yet part of approved continuity" in result["message"].lower()
    assert vault.approved_continuity_events(persona) == []


def test_get_boot_context_approved_continuity_unchanged_immediately_after_proposal(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    before = get_boot_context_handle({"persona": persona}, config=config)["approved_continuity"]

    handle(_base_input(persona=persona), config=config)

    after = get_boot_context_handle({"persona": persona}, config=config)["approved_continuity"]
    assert before == after == []


def test_committing_the_adapters_own_defer_intake_produces_no_approved_continuity(vault_with_persona) -> None:
    """A stronger boundary proof than "commit is unreachable": even if a
    human (or a test standing in for one) calls PersonaVault's own
    commit_session_intake directly on the exact intake this tool
    created, nothing becomes approved continuity, because every
    candidate this tool creates carries decision="defer" -- and defer
    candidates are explicitly skipped by commit_session_intake's own
    logic (they are "not yet decided," not "approved"). A rubber-stamp
    commit on the adapter's own output is not suffient to make anything
    canonical."""
    vault, config, persona = vault_with_persona
    result = handle(_base_input(persona=persona, text="A fact worth remembering."), config=config)

    vault.commit_session_intake(persona, result["intake_id"], reviewer="human-reviewer")

    assert vault.approved_continuity_events(persona) == []
    assert get_boot_context_handle({"persona": persona}, config=config)["approved_continuity"] == []


def test_human_commit_requires_a_genuinely_new_approve_intake_not_just_a_commit_call(vault_with_persona) -> None:
    """The only way an MCP-proposed fact becomes canonical: a human
    authors their own new intake against the same session, with
    decision="approve" -- an explicit authoring action, not a rubber
    stamp on the adapter's defer intake (see the test above). This is
    performed by the TEST, standing in for the human, using
    PersonaVault's own public API exactly as the desktop UI would --
    never by anything inside propose_session_note.py."""
    vault, config, persona = vault_with_persona
    proposal = handle(_base_input(persona=persona, text="A fact worth remembering."), config=config)

    human_intake = vault.save_session_intake(
        persona,
        proposal["session_id"],
        candidates=[{"category": "memory", "decision": "approve", "text": "A fact worth remembering."}],
        reviewer="human-reviewer",
    )
    vault.commit_session_intake(persona, human_intake["intake_id"], reviewer="human-reviewer")

    after = get_boot_context_handle({"persona": persona}, config=config)["approved_continuity"]
    assert len(after) == 1
    assert after[0]["type"] == "approved_memory"

    # The adapter's own defer intake is untouched -- it remains on
    # record as the proposal's own audit trail, separate from the
    # human's approving intake.
    assert vault.approved_continuity_events(persona)[0]["intake_id"] == human_intake["intake_id"]


def test_session_only_note_category_forces_session_only_review_state(vault_with_persona) -> None:
    """Preserves PersonaVault's own native behavior rather than
    reimplementing it: session_only_note candidates are forced to the
    session_only decision by _normalized_intake_candidates itself."""
    vault, config, persona = vault_with_persona
    result = handle(
        _base_input(persona=persona, category="session_only_note", text="Only relevant to this chat."),
        config=config,
    )
    assert result["review_state"] == "session_only"
    assert result["status"] == "pending_human_review"


# --- session mapping / duplicate behavior ------------------------------------

def test_two_calls_same_conversation_share_one_session(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    first = handle(_base_input(persona=persona, text="Fact one."), config=config)
    second = handle(_base_input(persona=persona, text="Fact two."), config=config)

    assert first["session_id"] == second["session_id"]
    assert first["intake_id"] != second["intake_id"]
    assert first["candidate_id"] != second["candidate_id"]


def test_repeated_identical_proposal_creates_independent_candidates_not_a_merge(vault_with_persona) -> None:
    """Verified native behavior: PersonaVault's own duplicate protection
    is scoped to commit-time (event_type, intake_id, candidate_id), and
    this tool always creates a fresh intake_id per call -- so an
    identical resubmission is NOT deduplicated at the proposal layer. It
    creates a second, independent, still-pending candidate. This is
    disclosed, verified behavior, not a bug and not invented dedup."""
    vault, config, persona = vault_with_persona
    payload = _base_input(persona=persona, text="Exactly the same fact, twice.")

    first = handle(payload, config=config)
    second = handle(dict(payload), config=config)

    assert first["session_id"] == second["session_id"]
    assert first["intake_id"] != second["intake_id"]
    assert first["candidate_id"] != second["candidate_id"]

    intake_dir = config.vault_root / "Active" / persona / "Chronicle" / "intake"
    assert (intake_dir / f"{first['intake_id']}.json").is_file()
    assert (intake_dir / f"{second['intake_id']}.json").is_file()


def test_same_text_different_conversation_id_creates_new_session(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    payload = _base_input(persona=persona, text="Same fact.")
    first = handle(payload, config=config)
    second = handle({**payload, "host_conversation_id": "conversation-2"}, config=config)
    assert first["session_id"] != second["session_id"]


def test_same_text_different_category_same_session_new_intake(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    payload = _base_input(persona=persona, text="Same text, different category.")
    first = handle({**payload, "category": "memory"}, config=config)
    second = handle({**payload, "category": "project_update"}, config=config)
    assert first["session_id"] == second["session_id"]
    assert first["intake_id"] != second["intake_id"]


def test_same_text_different_source_excerpt_same_session_new_intake(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    payload = _base_input(persona=persona, text="Same text again.")
    first = handle({**payload, "source_excerpt": "excerpt A"}, config=config)
    second = handle({**payload, "source_excerpt": "excerpt B"}, config=config)
    assert first["session_id"] == second["session_id"]
    assert first["intake_id"] != second["intake_id"]


def test_duplicate_proposal_error_is_reserved_but_unreachable() -> None:
    """Interface completeness only: the error class exists so a future
    slice could raise it if PersonaVault's own model ever grew
    proposal-time dedup, but nothing in Slice 3 raises it. Documented,
    not hidden."""
    assert DuplicateProposalError.code == "DUPLICATE_PROPOSAL"
    assert issubclass(DuplicateProposalError, Exception)


# --- unknown persona / archived resident -------------------------------------

def test_unknown_persona_returns_persona_not_found(vault_factory) -> None:
    _vault, config = vault_factory()
    with pytest.raises(PersonaNotFoundError) as excinfo:
        handle(_base_input(persona="Nobody Here"), config=config)
    assert excinfo.value.code == "PERSONA_NOT_FOUND"


def test_archived_resident_cannot_receive_a_proposal(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    vault.archive_persona(persona)
    with pytest.raises(PersonaNotFoundError):
        handle(_base_input(persona=persona), config=config)


def test_vault_unavailable_error_has_no_path_in_message(tmp_path) -> None:
    from personavault_mcp.config import AdapterConfig

    missing_root = tmp_path / "does-not-exist"
    config = AdapterConfig(
        vault_root=missing_root,
        personavault_source_path=__import__("pathlib").Path("/home/user/personavault"),
    )
    with pytest.raises(VaultUnavailableError) as excinfo:
        handle(_base_input(), config=config)
    message = str(excinfo.value)
    assert str(missing_root) not in message
    assert "Traceback" not in message


# --- partial-write behavior ---------------------------------------------------

def test_intake_save_failure_leaves_a_recoverable_orphan_session_not_corruption(
    vault_with_persona, monkeypatch
) -> None:
    """Step 1 (create_returned_session) succeeds and is durably written;
    step 2 (save_session_intake) fails. The session record must still
    exist on disk -- a legitimate, human-inspectable half-state -- and
    the call must not report success."""
    vault, config, persona = vault_with_persona

    original_save = type(vault).save_session_intake

    def _failing_save(self, *args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(type(vault), "save_session_intake", _failing_save)

    with pytest.raises(IntakeSaveFailureError):
        handle(_base_input(persona=persona, text="This should not be saved."), config=config)

    monkeypatch.setattr(type(vault), "save_session_intake", original_save)

    # The session itself was durably created despite the intake failure.
    sessions_dir = config.vault_root / "Active" / persona / "Chronicle" / "sessions"
    session_files = list(sessions_dir.glob("*.json"))
    assert len(session_files) == 1
    session_record = json.loads(session_files[0].read_text(encoding="utf-8"))
    assert session_record["schema_version"] == "session_return.v0.1"

    # No approved continuity was created by the failed attempt.
    assert vault.approved_continuity_events(persona) == []

    # A retry now succeeds and reuses the same (already cached) session,
    # rather than creating a second orphan.
    result = handle(_base_input(persona=persona, text="This one should be saved."), config=config)
    assert result["session_id"] == session_record["session_id"]


def test_adapter_failure_does_not_create_canonical_continuity(vault_with_persona, monkeypatch) -> None:
    vault, config, persona = vault_with_persona
    monkeypatch.setattr(
        type(vault),
        "save_session_intake",
        lambda self, *a, **k: (_ for _ in ()).throw(OSError("boom")),
    )
    with pytest.raises(IntakeSaveFailureError):
        handle(_base_input(persona=persona), config=config)
    assert vault.approved_continuity_events(persona) == []
    assert get_boot_context_handle({"persona": persona}, config=config)["approved_continuity"] == []


# --- documented PersonaVault Core finding (not a bug in this adapter) ------

def test_personavault_core_resolve_persona_dir_absolute_path_is_now_fixed(vault_factory) -> None:
    """Direct evidence against real PersonaVault Core with NO adapter
    guard in the way. Updated for the PersonaVault Core Maintenance Gate
    (Core commit d8b9762cf3371572383b72336cd1ad23f91f8dea):
    Vault._resolve_persona_dir now confines the direct-lookup join to
    the intended status directory itself, so this input cleanly raises
    FileNotFoundError -- the ordinary "not found" path -- instead of the
    uncaught NotADirectoryError this same test caught before that fix.
    persona_name_guard.py's own rejection remains in place as
    intentional defense-in-depth (it still returns MALFORMED_REQUEST
    before PersonaVault is even called, per
    test_path_like_persona_value_is_rejected_before_reaching_personavault),
    but Core itself no longer requires it to stay safe. Only run if
    /etc/passwd exists on the host (true for any ordinary Linux CI/dev
    box); harmless and read-only either way -- PersonaVault only ever
    attempts to read /etc/passwd/persona.yaml, which does not exist, so
    nothing is disclosed or written."""
    import pathlib

    if not pathlib.Path("/etc/passwd").is_file():
        pytest.skip("/etc/passwd not present on this host; finding not exercisable here.")

    vault, _config = vault_factory()
    with pytest.raises(FileNotFoundError):
        vault.create_returned_session("/etc/passwd", host_platform="direct-core-test")


# --- correlation cache shape --------------------------------------------------

def test_session_correlation_cache_key_shape() -> None:
    cache = SessionCorrelationCache()
    assert cache.get("PersonaA", "host1", "conv1") is None
    cache.put("PersonaA", "host1", "conv1", "session_abc")
    assert cache.get("PersonaA", "host1", "conv1") == "session_abc"
    # Different persona, host, or conversation -> different key, no
    # collision with the entry above.
    assert cache.get("PersonaB", "host1", "conv1") is None
    assert cache.get("PersonaA", "host2", "conv1") is None
    assert cache.get("PersonaA", "host1", "conv2") is None
