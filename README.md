# PersonaVault MCP Adapter

A host-neutral MCP adapter for PersonaVault. This repository is a **sibling**
to PersonaVault Core, never a fork or a mode of it. PersonaVault Core is only
ever used here as an imported dependency (once a later slice actually needs
it) — this repository never modifies PersonaVault Core, and PersonaVault
Core never depends on this repository.

## Current status: Slice 5 — a real local MCP service

As of this slice, `PersonaVault-MCP` is an actual, runnable local MCP
service, not just a tested library:

- Two functional MCP tools exist: `get_boot_context` (read-only) and
  `propose_session_note` (write-adjacent, proposal-only). Both are
  reachable over real **MCP Streamable HTTP** (spec `2025-11-25`), via
  the official `mcp` Python SDK (pinned `mcp>=1.30.0,<2` — see
  `server.py`'s module docstring for why 1.x, not 2.x).
  `propose_session_note` wraps PersonaVault's existing Session Return
  intake path and durably records `host_id`/`host_conversation_id`/a
  truthful `source="mcp_proposal"` — see the Slice 3/4 reports for how
  that boundary is enforced.
- **Start it**: `python -m personavault_mcp.server` or the console
  script `personavault-mcp` (after `pip install -e .`).
- **Binds to `127.0.0.1` only, by default, and by enforced policy** —
  `assert_bind_policy_is_safe` rejects startup outright for any
  non-loopback `bind_host` (see `config.py`). No authentication is
  required for this loopback-only mode; a non-loopback mode with real
  auth is explicitly deferred, not implemented.
- No public networking, tunnels, or remote hosting exist anywhere in
  this repository.
- PersonaVault is still referenced via a filesystem-path bridge
  (`personavault_bridge.py`), never a pip dependency — PersonaVault Core
  has no packaging metadata to install against.

See `docs/ARCHITECTURE_CONTRACT_V0_1.md` for the full design contract this
adapter is built against, including what its capability-boundary tests do
and do not guarantee, and the Slice 5 report for the full transport/auth
rationale.

## Running the tests

```bash
python3 -m pip install -e ".[dev]"
pytest
```

Includes real integration tests: a real `uvicorn`-served Streamable HTTP
server, a real `mcp` client, talking over real HTTP on an OS-assigned
loopback port per test — not mocked.

Tests exercise a real PersonaVault checkout (read-only, via
`personavault_bridge.py`) at a fixed path
(`tests/conftest.py:PERSONAVAULT_SOURCE_PATH`), currently
`/home/user/personavault`. This is a test-environment convenience, not a
hardcoded production path — `AdapterConfig.from_env()` reads
`PERSONAVAULT_MCP_SOURCE_PATH` for real use.

## Running the service

```bash
export PERSONAVAULT_MCP_SOURCE_PATH=/path/to/a/PersonaVault/checkout
export PERSONAVAULT_MCP_VAULT_ROOT=/path/to/a/PersonaVault/Library
python -m personavault_mcp.server
```

Serves Streamable HTTP at `http://127.0.0.1:8765/mcp` by default
(`PERSONAVAULT_MCP_BIND_HOST`/`PERSONAVAULT_MCP_BIND_PORT` to change the
bind address/port — non-loopback hosts are rejected at startup). See
`scripts/smoke_test.py` for a runnable, self-contained example using a
synthetic fixture persona (never a real one).

## Configuring PersonaVault access

Two distinct paths, never to be confused:

- `PERSONAVAULT_MCP_SOURCE_PATH` — where PersonaVault's *source code* is
  checked out, so it can be imported.
- `PERSONAVAULT_MCP_VAULT_ROOT` — where a persona *Library's data* lives
  (`Active/`, `Archive/`, `Exports/`, `AppConfig/`).

Neither is a pip package name — see `personavault_bridge.py` for why.

## Repository layout

```
src/personavault_mcp/   # the importable adapter package
tests/                  # capability-boundary and registry tests
docs/                   # design contract and related records
```
