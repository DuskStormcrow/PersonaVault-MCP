"""Slice 6 tests: the synthetic demo resident and isolated demo vault.

Exercises the real fixture builder against real, throwaway PersonaVault
vaults under pytest's tmp_path (never demo/vault itself, and never a
real PersonaVault Library), and verifies both MCP tools against the
built demo resident through the real Slice 5 Streamable HTTP service --
not mocked.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from personavault_mcp.config import AdapterConfig
from personavault_mcp.demo import build_demo_vault
from personavault_mcp.demo.fixture import (
    APPROVED_CONTINUITY_SEED,
    DEMO_PERSONA_NAME,
    DEMO_PROPOSAL_CATEGORY,
    DEMO_PROPOSAL_HOST_CONVERSATION_ID,
    DEMO_PROPOSAL_HOST_ID,
    DEMO_PROPOSAL_TEXT,
    REAL_RESIDENT_NAMES_NEVER_TO_USE,
)
from personavault_mcp.demo.safety import UnsafeDemoTargetError
from personavault_mcp.registry import APPROVED_TOOL_NAMES, reset_registry_for_tests
from personavault_mcp.server import build_app
from personavault_mcp.tools import get_boot_context, propose_session_note
from personavault_mcp.tools.propose_session_note import reset_session_cache_for_tests

PERSONAVAULT_SOURCE_PATH = Path("/home/user/personavault")


@pytest.fixture(autouse=True)
def _clean_state():
    reset_registry_for_tests()
    reset_session_cache_for_tests()
    yield
    reset_registry_for_tests()
    reset_session_cache_for_tests()


@pytest.fixture
def demo_vault_root(tmp_path, monkeypatch):
    """A real demo vault, freshly built under tmp_path -- never
    demo/vault itself. Ensures no PERSONAVAULT_MCP_VAULT_ROOT leaks in
    from the surrounding environment, so the safety-guard tests below
    control that variable deliberately."""
    monkeypatch.delenv("PERSONAVAULT_MCP_VAULT_ROOT", raising=False)
    return tmp_path / "demo_vault"


@pytest.fixture
def built_demo(demo_vault_root):
    result = build_demo_vault.build(demo_vault_root, PERSONAVAULT_SOURCE_PATH)
    config = AdapterConfig(
        vault_root=demo_vault_root, personavault_source_path=PERSONAVAULT_SOURCE_PATH
    )
    return result, config


# --- 1: demo builder creates the isolated vault -----------------------------


def test_builder_creates_isolated_vault(demo_vault_root):
    result = build_demo_vault.build(demo_vault_root, PERSONAVAULT_SOURCE_PATH)
    assert (demo_vault_root / "Active").is_dir()
    assert (demo_vault_root / ".personavault_demo_marker").is_file()
    assert result["persona_created"] is True
    assert result["persona_folder"]


# --- 2: builder is repeatable / idempotent ----------------------------------


def test_builder_is_idempotent(demo_vault_root):
    first = build_demo_vault.build(demo_vault_root, PERSONAVAULT_SOURCE_PATH)
    second = build_demo_vault.build(demo_vault_root, PERSONAVAULT_SOURCE_PATH)

    assert second["persona_created"] is False
    assert second["persona_folder"] == first["persona_folder"]
    assert second["continuity_events_appended"] == 0

    from personavault_mcp.personavault_bridge import ensure_personavault_importable

    ensure_personavault_importable(PERSONAVAULT_SOURCE_PATH)
    from personavault.storage import Vault

    vault = Vault(demo_vault_root)
    residents = [p for p in vault.list_personas("active") if p.manifest["name"] == DEMO_PERSONA_NAME]
    assert len(residents) == 1  # no duplicate persona created on rerun

    continuity = vault.approved_continuity_events(first["persona_folder"])
    assert len(continuity) == len(APPROVED_CONTINUITY_SEED)  # no duplicate events on rerun


# --- 3: builder cannot target the production vault root ---------------------


def test_builder_refuses_path_matching_configured_real_vault_root(tmp_path, monkeypatch):
    real_root = tmp_path / "real_library"
    monkeypatch.setenv("PERSONAVAULT_MCP_VAULT_ROOT", str(real_root))

    with pytest.raises(UnsafeDemoTargetError):
        build_demo_vault.build(real_root, PERSONAVAULT_SOURCE_PATH)


def test_builder_refuses_path_nested_inside_configured_real_vault_root(tmp_path, monkeypatch):
    real_root = tmp_path / "real_library"
    monkeypatch.setenv("PERSONAVAULT_MCP_VAULT_ROOT", str(real_root))

    with pytest.raises(UnsafeDemoTargetError):
        build_demo_vault.build(real_root / "demo" / "vault", PERSONAVAULT_SOURCE_PATH)


def test_reset_refuses_directory_without_demo_marker(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONAVAULT_MCP_VAULT_ROOT", raising=False)
    unrelated = tmp_path / "someone_elses_directory"
    unrelated.mkdir()
    (unrelated / "not_a_demo_marker.txt").write_text("real data", encoding="utf-8")

    with pytest.raises(UnsafeDemoTargetError):
        build_demo_vault.reset(unrelated)

    assert unrelated.is_dir()  # untouched


def test_reset_accepts_a_directory_it_marked_itself(demo_vault_root):
    build_demo_vault.build(demo_vault_root, PERSONAVAULT_SOURCE_PATH)
    assert demo_vault_root.exists()
    build_demo_vault.reset(demo_vault_root)
    assert not demo_vault_root.exists()


# --- 4: no real resident names appear in demo fixture content ---------------


def test_no_real_resident_names_in_fixture_content(built_demo):
    result, config = built_demo
    from personavault_mcp.personavault_bridge import ensure_personavault_importable

    ensure_personavault_importable(PERSONAVAULT_SOURCE_PATH)
    from personavault.storage import Vault

    vault = Vault(config.vault_root)
    package = vault.load_persona(result["persona_folder"])
    preview = vault.boot_package_preview(result["persona_folder"])

    haystacks = [
        DEMO_PERSONA_NAME,
        preview["boot_prompt"],
        preview["memory_rules"],
        json.dumps(package.manifest),
        *(item["text"] for item in APPROVED_CONTINUITY_SEED),
        DEMO_PROPOSAL_TEXT,
    ]
    full_text = "\n".join(haystacks).lower()
    for forbidden_name in REAL_RESIDENT_NAMES_NEVER_TO_USE:
        # Word-boundary match: a bare substring check would false-positive
        # on ordinary English words that happen to contain a short name
        # (e.g. "Eve" inside PersonaVault Core's own boilerplate "presERVE").
        pattern = r"\b" + re.escape(forbidden_name.lower()) + r"\b"
        assert not re.search(pattern, full_text), forbidden_name


# --- 5: synthetic resident loads successfully -------------------------------


def test_synthetic_resident_loads_successfully(built_demo):
    result, config = built_demo
    from personavault_mcp.personavault_bridge import ensure_personavault_importable

    ensure_personavault_importable(PERSONAVAULT_SOURCE_PATH)
    from personavault.storage import Vault

    vault = Vault(config.vault_root)
    package = vault.load_persona(result["persona_folder"])
    assert package.manifest["name"] == DEMO_PERSONA_NAME


# --- 6, 7: get_boot_context returns expected identity/context, bounded -----


def test_get_boot_context_returns_expected_identity_and_bounded_continuity(built_demo):
    result, config = built_demo
    payload = get_boot_context.handle({"persona": result["persona_folder"]}, config=config)

    assert payload["persona_name"] == DEMO_PERSONA_NAME
    assert payload["boot_prompt"]
    assert payload["memory_rules"]
    assert payload["memory_behavior"]
    assert payload["doctrine"]
    assert payload["host_boundary"]

    assert len(payload["approved_continuity"]) == len(APPROVED_CONTINUITY_SEED)
    assert len(payload["approved_continuity"]) <= payload["approved_continuity_limit"]
    assert set(payload.keys()) == set(get_boot_context.ALLOWED_OUTPUT_FIELDS)


# --- 8: proposed demo fact is absent before proposal ------------------------


def test_proposal_text_absent_from_approved_continuity_before_proposal(built_demo):
    result, config = built_demo
    payload = get_boot_context.handle({"persona": result["persona_folder"]}, config=config)
    # Approved continuity events store their text under "summary"
    # (personavault.storage.Vault._approved_continuity_event), not "text"
    # -- verified directly against Core, not assumed.
    all_text = " ".join(event.get("summary", "") for event in payload["approved_continuity"])
    assert DEMO_PROPOSAL_TEXT not in all_text


# --- 9, 10, 11, 12: propose_session_note succeeds, stays pending/defer, ----
# --- approved continuity unchanged, host provenance synthetic and correct --


def _read_session_record(config, persona: str, session_id: str) -> dict:
    path = config.vault_root / "Active" / persona / "Chronicle" / "sessions" / f"{session_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_propose_session_note_demo_scenario_end_to_end(built_demo):
    result, config = built_demo
    persona = result["persona_folder"]

    before = get_boot_context.handle({"persona": persona}, config=config)

    proposal_result = propose_session_note.handle(
        {
            "persona": persona,
            "host_id": DEMO_PROPOSAL_HOST_ID,
            "host_conversation_id": DEMO_PROPOSAL_HOST_CONVERSATION_ID,
            "category": DEMO_PROPOSAL_CATEGORY,
            "text": DEMO_PROPOSAL_TEXT,
        },
        config=config,
    )

    assert proposal_result["status"] == "pending_human_review"
    assert proposal_result["review_state"] == "defer"

    record = _read_session_record(config, persona, proposal_result["session_id"])
    assert record["host_conversation_id"] == DEMO_PROPOSAL_HOST_CONVERSATION_ID
    assert record["host_platform"] == DEMO_PROPOSAL_HOST_ID
    assert record["source"] == propose_session_note.MCP_SESSION_SOURCE

    after = get_boot_context.handle({"persona": persona}, config=config)
    assert after["approved_continuity"] == before["approved_continuity"]
    assert len(after["approved_continuity"]) == len(APPROVED_CONTINUITY_SEED)


# --- 13: demo reset affects only demo data ----------------------------------


def test_reset_does_not_touch_a_sibling_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONAVAULT_MCP_VAULT_ROOT", raising=False)
    demo_root = tmp_path / "demo_vault"
    sibling = tmp_path / "sibling_untouched"
    sibling.mkdir()
    (sibling / "keep_me.txt").write_text("do not delete", encoding="utf-8")

    build_demo_vault.build(demo_root, PERSONAVAULT_SOURCE_PATH)
    build_demo_vault.reset(demo_root)

    assert not demo_root.exists()
    assert (sibling / "keep_me.txt").is_file()


# --- 14: exactly two MCP tools remain exposed -------------------------------


def test_exactly_two_mcp_tools_remain_exposed(built_demo):
    result, config = built_demo
    app = build_app(config)
    starlette_app = app.streamable_http_app()

    uvicorn_config = uvicorn.Config(starlette_app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(uvicorn_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("Test server did not start in time.")
        port = server.servers[0].sockets[0].getsockname()[1]
        url = f"http://127.0.0.1:{port}/mcp"

        async def _list_tools():
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client

            async with streamable_http_client(url) as (read, write, _sid):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.list_tools()

        tools = asyncio.run(_list_tools())
        names = sorted(t.name for t in tools.tools)
        assert names == sorted(APPROVED_TOOL_NAMES) == ["get_boot_context", "propose_session_note"]
    finally:
        server.should_exit = True
        thread.join(timeout=5)


# --- 15, 16: no new public networking, no vendor-specific runtime code -----


def test_demo_fixture_module_has_no_networking_or_vendor_code():
    import inspect

    from personavault_mcp.demo import build_demo_vault as module
    from personavault_mcp.demo import fixture as fixture_module

    source = inspect.getsource(module) + inspect.getsource(fixture_module)
    lowered = source.lower()
    for forbidden in ("socket.", "0.0.0.0", "alexa", "amazon", "nebius", "nemotron"):
        assert forbidden not in lowered, forbidden
