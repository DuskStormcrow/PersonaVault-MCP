# PersonaVault MCP Adapter

A host-neutral MCP adapter for PersonaVault. This repository is a **sibling**
to PersonaVault Core, never a fork or a mode of it. PersonaVault Core is only
ever used here as an imported dependency (once a later slice actually needs
it) — this repository never modifies PersonaVault Core, and PersonaVault
Core never depends on this repository.

## Current status: Slice 1 — adapter skeleton + capability-boundary tests

This is the smallest possible foundation, built to prove the architecture
boundary *before* any functional MCP tool exists. As of this slice:

- No MCP tool is implemented. `get_boot_context` and `propose_session_note`
  do not exist yet — only their approved *names* are reserved in
  `personavault_mcp.registry.APPROVED_TOOL_NAMES`.
- No dependency on the `personavault` package exists yet.
- No networking, no transport, no authentication is wired up.
- No demo/simulator client exists in this repository.

See `docs/ARCHITECTURE_CONTRACT_V0_1.md` for the full design contract this
adapter is built against, including what its capability-boundary tests do
and do not guarantee.

## Running the tests

```bash
python3 -m pip install -e ".[dev]"
pytest
```

## Repository layout

```
src/personavault_mcp/   # the importable adapter package
tests/                  # capability-boundary and registry tests
docs/                   # design contract and related records
```
