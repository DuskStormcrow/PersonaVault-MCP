"""Slice 5 integration tests: a real uvicorn-served Streamable HTTP MCP
server, a real MCP client (mcp.client.streamable_http +
mcp.ClientSession), talking over real HTTP on loopback -- not mocked.

Each test gets its own server bound to an OS-assigned ephemeral port
(port=0), so tests can run in parallel without colliding, and its own
fresh, throwaway PersonaVault vault + persona (never a checked-in demo
resident).
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path

import pytest
import uvicorn

from personavault_mcp.config import AdapterConfig
from personavault_mcp.registry import APPROVED_TOOL_NAMES, reset_registry_for_tests
from personavault_mcp.server import build_app
from personavault_mcp.tools.propose_session_note import reset_session_cache_for_tests

PERSONAVAULT_SOURCE_PATH = Path("/home/user/personavault")


@pytest.fixture(autouse=True)
def _clean_state():
    reset_registry_for_tests()
    reset_session_cache_for_tests()
    yield
    reset_registry_for_tests()
    reset_session_cache_for_tests()


class _RunningServer:
    def __init__(self, port: int, config: AdapterConfig):
        self.port = port
        self.config = config

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/mcp"


@pytest.fixture
def running_server(vault_with_persona):
    """Starts a real server on an OS-assigned free port, bound to
    127.0.0.1, serving the given fixture vault. Tears it down after the
    test regardless of outcome."""
    vault, config, persona = vault_with_persona
    app = build_app(config)
    starlette_app = app.streamable_http_app()

    uvicorn_config = uvicorn.Config(starlette_app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(uvicorn_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(100):
        if server.started:
            break
        import time

        time.sleep(0.05)
    else:
        raise RuntimeError("Test server did not start in time.")

    actual_port = server.servers[0].sockets[0].getsockname()[1]

    yield _RunningServer(actual_port, config), persona

    server.should_exit = True
    thread.join(timeout=5)


async def _list_tools(url: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(url) as (read, write, _sid):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.list_tools()


async def _call_tool(url: str, name: str, arguments: dict):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(url) as (read, write, _sid):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(name, arguments)


def _text_of(result) -> str:
    return next(block.text for block in result.content if getattr(block, "type", None) == "text")


# --- 4, 5: exactly two tools advertised, matching the registry --------------

def test_exactly_two_tools_advertised_matching_registry(running_server) -> None:
    server, _persona = running_server
    tools = asyncio.run(_list_tools(server.url))
    names = sorted(t.name for t in tools.tools)
    assert names == sorted(APPROVED_TOOL_NAMES) == ["get_boot_context", "propose_session_note"]


# --- 6: get_boot_context invocable through real transport -------------------

def test_get_boot_context_invocable_through_real_transport(running_server) -> None:
    server, persona = running_server
    result = asyncio.run(_call_tool(server.url, "get_boot_context", {"persona": persona}))
    assert not result.isError
    payload = json.loads(_text_of(result))
    assert payload["persona_name"]
    assert payload["approved_continuity"] == []


# --- 7: propose_session_note invocable through real transport --------------

def test_propose_session_note_invocable_through_real_transport(running_server) -> None:
    server, persona = running_server
    result = asyncio.run(
        _call_tool(
            server.url,
            "propose_session_note",
            {
                "persona": persona,
                "host_id": "integration-test-host",
                "host_conversation_id": "integration-test-conversation",
                "category": "memory",
                "text": "A fact proposed through real Streamable HTTP.",
            },
        )
    )
    assert not result.isError
    payload = json.loads(_text_of(result))
    assert payload["status"] == "pending_human_review"
    assert payload["review_state"] == "defer"


# --- 8: malformed input rejected through transport --------------------------

@pytest.mark.parametrize(
    "bad_arguments",
    [
        {},  # missing everything
        {"persona": "x"},  # missing required fields
        {
            "persona": "x",
            "host_id": "h",
            "host_conversation_id": "c",
            "category": "not_a_real_category",
            "text": "t",
        },
    ],
)
def test_malformed_input_rejected_through_transport(running_server, bad_arguments) -> None:
    server, _persona = running_server
    result = asyncio.run(_call_tool(server.url, "propose_session_note", bad_arguments))
    assert result.isError


# --- 9: decision=approve rejected through transport --------------------------

def test_decision_approve_rejected_through_transport(running_server) -> None:
    server, persona = running_server
    result = asyncio.run(
        _call_tool(
            server.url,
            "propose_session_note",
            {
                "persona": persona,
                "host_id": "h",
                "host_conversation_id": "c",
                "category": "memory",
                "text": "Attempted smuggled approval.",
                "decision": "approve",
            },
        )
    )
    assert result.isError


# --- 10: unknown tool name fails cleanly ------------------------------------

def test_unknown_tool_name_fails_cleanly(running_server) -> None:
    server, _persona = running_server
    result = asyncio.run(_call_tool(server.url, "commit_session_intake", {"persona": "x"}))
    assert result.isError
    assert "UNSUPPORTED_OPERATION" in _text_of(result)


# --- 11: adapter errors sanitized (no path leak) through transport ---------

def test_adapter_errors_are_sanitized_through_transport(running_server) -> None:
    server, _persona = running_server
    result = asyncio.run(_call_tool(server.url, "get_boot_context", {"persona": "Nobody Here"}))
    assert result.isError
    text = _text_of(result)
    assert "PERSONA_NOT_FOUND" in text
    assert str(server.config.vault_root) not in text
    assert "Traceback" not in text


# --- 12: response payloads expose only allowed fields -----------------------

def test_response_payload_exposes_only_allowed_fields(running_server) -> None:
    from personavault_mcp.tools.get_boot_context import ALLOWED_OUTPUT_FIELDS

    server, persona = running_server
    result = asyncio.run(_call_tool(server.url, "get_boot_context", {"persona": persona}))
    payload = json.loads(_text_of(result))
    assert set(payload.keys()) == set(ALLOWED_OUTPUT_FIELDS)


# --- 15: startup failure on occupied port is clean --------------------------

def test_startup_fails_cleanly_on_occupied_port(vault_with_persona) -> None:
    """Verified directly against the installed uvicorn: a bind failure
    (address already in use) does not propagate as a plain OSError from
    server.serve()/run() -- uvicorn's own startup path catches it
    internally and calls sys.exit(STARTUP_FAILURE), already logging a
    clear error itself. personavault_mcp.server.main() catches exactly
    that SystemExit and returns the same code cleanly (see
    test_main_returns_startup_failure_code_on_occupied_port below for
    that layer); this test proves the underlying behavior main() relies
    on."""
    import socket

    from uvicorn.server import STARTUP_FAILURE

    vault, config, _persona = vault_with_persona

    occupied_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied_socket.bind(("127.0.0.1", 0))
    occupied_socket.listen(1)
    occupied_port = occupied_socket.getsockname()[1]

    try:
        conflicting_config = AdapterConfig(
            vault_root=config.vault_root,
            personavault_source_path=config.personavault_source_path,
            bind_host="127.0.0.1",
            bind_port=occupied_port,
        )
        app = build_app(conflicting_config)
        starlette_app = app.streamable_http_app()
        uvicorn_config = uvicorn.Config(
            starlette_app, host="127.0.0.1", port=occupied_port, log_level="warning"
        )
        server = uvicorn.Server(uvicorn_config)

        with pytest.raises(SystemExit) as excinfo:
            asyncio.run(server.serve())
        assert excinfo.value.code == STARTUP_FAILURE
    finally:
        occupied_socket.close()


def test_main_returns_startup_failure_code_on_occupied_port(vault_with_persona, monkeypatch) -> None:
    """The actual entry point: main() must return the same clean,
    non-zero code rather than let a bare SystemExit escape or silently
    pick a different port."""
    import socket

    from uvicorn.server import STARTUP_FAILURE

    import personavault_mcp.server as server_module

    vault, config, _persona = vault_with_persona

    occupied_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied_socket.bind(("127.0.0.1", 0))
    occupied_socket.listen(1)
    occupied_port = occupied_socket.getsockname()[1]

    try:
        monkeypatch.setenv("PERSONAVAULT_MCP_VAULT_ROOT", str(config.vault_root))
        monkeypatch.setenv("PERSONAVAULT_MCP_SOURCE_PATH", str(config.personavault_source_path))
        monkeypatch.setenv("PERSONAVAULT_MCP_BIND_HOST", "127.0.0.1")
        monkeypatch.setenv("PERSONAVAULT_MCP_BIND_PORT", str(occupied_port))

        exit_code = server_module.main()
        assert exit_code == STARTUP_FAILURE
    finally:
        occupied_socket.close()


# --- logging content safety (13, 14) ----------------------------------------
#
# Scoped deliberately to personavault_mcp.server's own logger, not every
# logger active in the process: the mcp *client* SDK (mcp.client.*) logs
# its own outgoing request payloads at DEBUG level, which legitimately
# includes the proposal text -- that is the caller's own client-side
# debug trace of what it sent, on its own machine, not something our
# server controls, produces, or would be responsible for in a real
# deployment where client and server are different processes entirely.
# What this adapter owns and must keep clean is its OWN service log.

def _own_server_log_text(caplog) -> str:
    return "\n".join(
        record.getMessage() for record in caplog.records if record.name == "personavault_mcp.server"
    )


def test_logs_do_not_contain_proposal_text(running_server, caplog) -> None:
    server, persona = running_server
    distinctive_text = "UNIQUE_MARKER_A1B2C3_PROPOSAL_TEXT"
    with caplog.at_level(logging.DEBUG, logger="personavault_mcp.server"):
        asyncio.run(
            _call_tool(
                server.url,
                "propose_session_note",
                {
                    "persona": persona,
                    "host_id": "h",
                    "host_conversation_id": "c",
                    "category": "memory",
                    "text": distinctive_text,
                    "source_excerpt": "UNIQUE_MARKER_EXCERPT_D4E5F6",
                },
            )
        )
    own_log_text = _own_server_log_text(caplog)
    assert "tool invocation succeeded: propose_session_note" in own_log_text
    assert distinctive_text not in own_log_text
    assert "UNIQUE_MARKER_EXCERPT_D4E5F6" not in own_log_text


def test_logs_do_not_contain_boot_context_contents(running_server, caplog) -> None:
    server, persona = running_server
    with caplog.at_level(logging.DEBUG, logger="personavault_mcp.server"):
        result = asyncio.run(_call_tool(server.url, "get_boot_context", {"persona": persona}))
    payload = json.loads(_text_of(result))
    boot_prompt_text = payload["boot_prompt"]
    assert boot_prompt_text, "fixture must have non-empty boot_prompt for this test to be meaningful"

    own_log_text = _own_server_log_text(caplog)
    assert "tool invocation succeeded: get_boot_context" in own_log_text
    assert boot_prompt_text not in own_log_text
    assert payload["memory_rules"] not in own_log_text
