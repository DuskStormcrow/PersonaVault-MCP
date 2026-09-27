"""Manual smoke test for Slice 5: start the real server, connect a real
MCP client over real Streamable HTTP, list tools, call both tools
against a synthetic, throwaway PersonaVault fixture, and shut down.

Not part of the pytest suite (see tests/test_server_integration.py for
the automated equivalent) -- this is the standalone script referenced
in the Slice 5 report's "Manual smoke test" section, runnable on its
own:

    PYTHONPATH=src python3 scripts/smoke_test.py

Uses a synthetic fixture persona created fresh in a tempdir. No real
PersonaVault resident is used or required.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn

PERSONAVAULT_SOURCE_PATH = Path("/home/user/personavault")
PORT = 18765


def _build_synthetic_vault(vault_root: Path) -> str:
    import sys

    sys.path.insert(0, str(PERSONAVAULT_SOURCE_PATH))
    from personavault.models import PersonaDraft
    from personavault.storage import Vault

    vault = Vault(vault_root)
    vault.initialize()
    package = vault.create_persona(PersonaDraft(name="Smoke Test Synthetic"))
    return package.path.name


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        vault_root = Path(tmp) / "vault"
        persona = _build_synthetic_vault(vault_root)
        print(f"[1/7] Synthetic fixture created: persona folder = {persona!r}")

        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from personavault_mcp.config import AdapterConfig
        from personavault_mcp.server import build_app

        config = AdapterConfig(
            vault_root=vault_root,
            personavault_source_path=PERSONAVAULT_SOURCE_PATH,
            bind_host="127.0.0.1",
            bind_port=PORT,
        )
        app = build_app(config)
        starlette_app = app.streamable_http_app()
        uvicorn_config = uvicorn.Config(starlette_app, host="127.0.0.1", port=PORT, log_level="warning")
        server = uvicorn.Server(uvicorn_config)

        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(50):
            if server.started:
                break
            time.sleep(0.1)
        print(f"[2/7] Service started on http://127.0.0.1:{PORT}/mcp")

        asyncio.run(_run_client(persona))

        server.should_exit = True
        thread.join(timeout=5)
        print("[7/7] Service shut down.")


async def _run_client(persona: str) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    url = f"http://127.0.0.1:{PORT}/mcp"
    async with streamable_http_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"[3/7] Tools listed: {names}")
            assert names == ["get_boot_context", "propose_session_note"], names

            boot_result = await session.call_tool("get_boot_context", {"persona": persona})
            assert not boot_result.isError, boot_result.content
            print("[4/7] get_boot_context called successfully.")

            propose_result = await session.call_tool(
                "propose_session_note",
                {
                    "persona": persona,
                    "host_id": "smoke_test_client",
                    "host_conversation_id": "smoke-test-conversation",
                    "category": "memory",
                    "text": "Synthetic smoke-test fact -- not a real memory.",
                },
            )
            assert not propose_result.isError, propose_result.content
            print("[5/7] propose_session_note called successfully.")

            payload_text = next(
                block.text for block in propose_result.content if getattr(block, "type", None) == "text"
            )
            payload = json.loads(payload_text)
            assert payload["status"] == "pending_human_review"
            assert payload["review_state"] == "defer"
            print(
                f"[6/7] Confirmed pending human review: status={payload['status']!r}, "
                f"review_state={payload['review_state']!r}"
            )


if __name__ == "__main__":
    main()
