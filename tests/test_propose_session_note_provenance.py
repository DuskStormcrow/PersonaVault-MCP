"""Slice 4 tests: provenance hardening.

Verifies that host_id, host_conversation_id, and a truthful MCP-origin
source are now durably persisted by PersonaVault itself (via the real,
native create_returned_session parameters added in the Core Maintenance
Gate), and precisely documents what does and does not survive an
adapter restart now that provenance -- but not correlation -- is
durable.
"""

from __future__ import annotations

import json

import pytest

from personavault_mcp.tools.propose_session_note import (
    MCP_SESSION_SOURCE,
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


def _read_session_record(config, persona: str, session_id: str) -> dict:
    path = config.vault_root / "Active" / persona / "Chronicle" / "sessions" / f"{session_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --- 1, 2: host_id / host_conversation_id persisted --------------------------

def test_host_conversation_id_is_persisted_in_session_record(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    result = handle(
        _base_input(persona=persona, host_conversation_id="conversation-abc"), config=config
    )
    record = _read_session_record(config, persona, result["session_id"])
    assert record["host_conversation_id"] == "conversation-abc"


def test_host_id_is_persisted_as_host_platform(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    result = handle(_base_input(persona=persona, host_id="claude_desktop"), config=config)
    record = _read_session_record(config, persona, result["session_id"])
    assert record["host_platform"] == "claude_desktop"


# --- 3, 4: source distinguishes MCP from manual ------------------------------

def test_mcp_created_session_uses_the_mcp_source_value(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    result = handle(_base_input(persona=persona), config=config)
    record = _read_session_record(config, persona, result["session_id"])
    assert record["source"] == MCP_SESSION_SOURCE == "mcp_proposal"
    assert record["source"] != "manual_user_entry"


def test_manually_created_session_still_defaults_to_manual_user_entry(vault_with_persona) -> None:
    """A session created directly through PersonaVault's own API (as the
    desktop UI does, and exactly as this test stands in for it) must be
    completely unaffected by this tool's own source choice -- proves the
    default wasn't changed at the Core level, only the adapter's own
    explicit choice."""
    vault, config, persona = vault_with_persona
    session = vault.create_returned_session(persona, summary="Manual desktop entry.")
    assert session["source"] == "manual_user_entry"


# --- 5: two conversations remain distinguishable -----------------------------

def test_two_different_conversation_ids_remain_distinguishable(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    first = handle(_base_input(persona=persona, host_conversation_id="conversation-A"), config=config)
    second = handle(_base_input(persona=persona, host_conversation_id="conversation-B"), config=config)

    assert first["session_id"] != second["session_id"]
    first_record = _read_session_record(config, persona, first["session_id"])
    second_record = _read_session_record(config, persona, second["session_id"])
    assert first_record["host_conversation_id"] == "conversation-A"
    assert second_record["host_conversation_id"] == "conversation-B"


# --- 6: same conversation within one process reuses the session, and -------
# --- the durable record reflects it consistently across both calls ---------

def test_same_conversation_within_one_process_reuses_session_and_provenance(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    payload = _base_input(persona=persona, host_conversation_id="conversation-same")

    first = handle({**payload, "text": "First fact."}, config=config)
    second = handle({**payload, "text": "Second fact."}, config=config)

    assert first["session_id"] == second["session_id"]
    record = _read_session_record(config, persona, first["session_id"])
    assert record["host_conversation_id"] == "conversation-same"
    assert record["source"] == MCP_SESSION_SOURCE


# --- 7: provenance survives clearing the in-memory correlation cache -------

def test_provenance_survives_clearing_the_correlation_cache(vault_with_persona) -> None:
    """Simulates an adapter restart: the in-memory correlation cache is
    cleared, but the already-created session's durable record on disk
    must be completely unaffected -- host_conversation_id and source
    read back exactly as they were written, with no dependency on the
    cache that no longer holds them."""
    vault, config, persona = vault_with_persona
    result = handle(
        _base_input(persona=persona, host_conversation_id="conversation-durable"), config=config
    )

    reset_session_cache_for_tests()  # simulates the adapter process restarting

    record = _read_session_record(config, persona, result["session_id"])
    assert record["host_conversation_id"] == "conversation-durable"
    assert record["source"] == MCP_SESSION_SOURCE
    assert record["host_platform"] == "test-host"


# --- 9: documented duplicate-session-after-restart behavior -----------------
# (item 8, rediscovery, does not apply: verified no public PersonaVault
# API exists to look up a returned session by persona/host/conversation
# id -- see session_correlation.py's module docstring and the Slice 4
# report. This test documents outcome B precisely, rather than pretend
# otherwise.)

def test_restart_without_rediscovery_creates_a_second_independent_session(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    payload = _base_input(persona=persona, host_conversation_id="conversation-restart")

    before_restart = handle({**payload, "text": "Before restart."}, config=config)

    reset_session_cache_for_tests()  # simulates the adapter process restarting

    after_restart = handle({**payload, "text": "After restart."}, config=config)

    # A second, independent session is created -- not a resumption of
    # the first. This is the disclosed, verified limitation, not
    # something this test pretends is otherwise.
    assert after_restart["session_id"] != before_restart["session_id"]

    # Both sessions remain fully intact, correctly provenanced, and
    # independently discoverable by a human reviewing PersonaVault
    # directly -- nothing was lost, only the automatic re-linking.
    first_record = _read_session_record(config, persona, before_restart["session_id"])
    second_record = _read_session_record(config, persona, after_restart["session_id"])
    assert first_record["host_conversation_id"] == "conversation-restart"
    assert second_record["host_conversation_id"] == "conversation-restart"
    assert first_record["source"] == second_record["source"] == MCP_SESSION_SOURCE


# --- 15: no brand-specific terminology in provenance values -----------------

def test_mcp_session_source_is_host_neutral() -> None:
    assert "alexa" not in MCP_SESSION_SOURCE.lower()
    assert "amazon" not in MCP_SESSION_SOURCE.lower()


def test_persisted_provenance_values_contain_no_brand_terminology(vault_with_persona) -> None:
    vault, config, persona = vault_with_persona
    result = handle(
        _base_input(persona=persona, host_id="simulated_alexa_plus_demo_client"), config=config
    )
    record = _read_session_record(config, persona, result["session_id"])
    # host_id itself is an opaque, host-supplied string -- a caller may
    # legitimately name itself anything, including something that
    # mentions a real host for its own demo purposes. What matters is
    # that PersonaVault Core's and this adapter's OWN generated values
    # (source) never do, regardless of what a caller supplies for
    # host_id.
    assert record["source"] == "mcp_proposal"
    assert "alexa" not in record["source"].lower()
    assert "amazon" not in record["source"].lower()
