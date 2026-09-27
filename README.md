# PersonaVault MCP Adapter

A host-neutral MCP adapter for PersonaVault. This repository is a **sibling**
to PersonaVault Core, never a fork or a mode of it. PersonaVault Core is only
ever used here as an imported dependency (once a later slice actually needs
it) — this repository never modifies PersonaVault Core, and PersonaVault
Core never depends on this repository.

## Current status: Slice 3 — two functional tools

As of this slice:

- Two functional MCP tools exist: `get_boot_context` (read-only, Slice 2)
  and `propose_session_note` (write-adjacent, proposal-only, Slice 3).
  Neither is auto-registered on import — call
  `personavault_mcp.bootstrap.register_default_tools()` explicitly.
- `propose_session_note` wraps PersonaVault's existing Session Return
  intake path (`create_returned_session` → `save_session_intake`). It
  never calls `commit_session_intake` and cannot produce an "approve"
  decision — every candidate lands as `defer` (or natively
  `session_only` for that one category), pending human review inside
  PersonaVault.
- PersonaVault is referenced via a filesystem-path bridge
  (`personavault_bridge.py`), not a pip dependency — PersonaVault Core has
  no packaging metadata to install against.
- `persona_name_guard.py` rejects any path-shaped `persona` input before
  PersonaVault ever sees it — a real PersonaVault Core issue found during
  Slice 3 (see the Slice 3 report and that module's docstring).
- Two small, additive PersonaVault Core changes are recommended but
  **not implemented** — see `docs/ARCHITECTURE_CONTRACT_V0_1.md`'s
  Slice 3 notes for the precise proposals, pending separate review.
- Still no networking, no transport, no authentication beyond what Slice 1
  established, and no demo/simulator client in this repository.

See `docs/ARCHITECTURE_CONTRACT_V0_1.md` for the full design contract this
adapter is built against, including what its capability-boundary tests do
and do not guarantee.

## Running the tests

```bash
python3 -m pip install -e ".[dev]"
pytest
```

Tests exercise a real PersonaVault checkout (read-only, via
`personavault_bridge.py`) at a fixed path
(`tests/conftest.py:PERSONAVAULT_SOURCE_PATH`), currently
`/home/user/personavault`. This is a test-environment convenience, not a
hardcoded production path — `AdapterConfig.from_env()` reads
`PERSONAVAULT_MCP_SOURCE_PATH` for real use.

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
