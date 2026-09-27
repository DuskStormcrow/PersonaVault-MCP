# PersonaVault MCP Adapter

A host-neutral MCP adapter for PersonaVault. This repository is a **sibling**
to PersonaVault Core, never a fork or a mode of it. PersonaVault Core is only
ever used here as an imported dependency (once a later slice actually needs
it) — this repository never modifies PersonaVault Core, and PersonaVault
Core never depends on this repository.

## Current status: Slice 2 — one functional tool, `get_boot_context`

As of this slice:

- Exactly one functional MCP tool exists: `get_boot_context`, a read-only,
  bounded projection of `Vault.boot_package_preview()`. It is not
  auto-registered on import — call
  `personavault_mcp.bootstrap.register_default_tools()` explicitly.
- `propose_session_note` remains a reserved name only, in
  `personavault_mcp.registry.APPROVED_TOOL_NAMES` — no handler exists.
- PersonaVault is referenced via a filesystem-path bridge
  (`personavault_bridge.py`), not a pip dependency — PersonaVault Core has
  no packaging metadata to install against. See that module's docstring
  for why, and the Slice 2 report for the discovered constraint this
  reflects.
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
