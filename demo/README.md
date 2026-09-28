# PersonaVault-MCP demo fixture

A completely synthetic PersonaVault resident and an isolated demo vault,
safe for MCP smoke tests, screenshots, recordings, public demo material,
and hackathon judging.

**All resident data on this page and in the vault it describes is
fictional.** Nothing here was copied, adapted, anonymized, or lightly
disguised from any real PersonaVault resident.

## What the synthetic resident is

**Rook** is a PersonaVault resident generated entirely from PersonaVault
Core's own stock "No-Nonsense Work Partner" guided-creation recipe — the
same recipe any real user can pick from the ordinary guided-creation
flow, unmodified. Rook has:

- an identity, temperament, values, and relationship stance (all the
  recipe's own generic stock content);
- a memory mode (`task_project_memory`);
- a full guided-creation boot prompt and memory rules, generated the
  same way PersonaVault generates them for any real resident;
- three already-**approved** continuity events, seeded through
  PersonaVault's real Session Return review path (not written directly
  into storage), so they are a faithful example of what approved
  continuity actually looks like on disk:
  1. a **preference** — prefers concise, technical explanations;
  2. a **completed task** — finished a sample project inventory with no
     blocking issues;
  3. a **relationship/workflow fact** — works with the user mainly
     weekday mornings and likes a short status update first.

See `src/personavault_mcp/demo/fixture.py` for the exact content (data
only, no logic) and `REAL_RESIDENT_NAMES_NEVER_TO_USE` for the explicit
list of real residents this fixture must never resemble.

## Why it exists

PersonaVault-MCP's own tests already build fresh, throwaway fixtures for
every test (see `tests/conftest.py`). This is different: a **stable,
polished, disposable-but-recognizable** fixture meant to be looked at by
people — for a demo recording, a screenshot, or a judge poking at the
running service directly — where a randomly-generated per-test persona
would be confusing or, worse, risk a real resident's data ending up on
screen by accident.

## How to build / reset the demo vault

From the repository root, with `pip install -e .` already done:

```bash
python -m personavault_mcp.demo.build_demo_vault
```

This creates `demo/vault/` (this directory) if it does not exist,
creates Rook if not already present, and seeds the three approved
continuity events if they are not already there. **Safe to re-run** —
an existing resident and its continuity are left exactly as they are,
never duplicated.

To wipe it and start over:

```bash
python -m personavault_mcp.demo.build_demo_vault --reset
```

`demo/vault/` is disposable and rebuildable — it is not checked into
git (see `.gitignore`), and destructive reset is confined strictly to a
directory the builder itself marked as a demo vault (see
`src/personavault_mcp/demo/safety.py`); it never touches, infers, or
requires a real PersonaVault Library.

## How to start PersonaVault-MCP against it

```bash
PERSONAVAULT_MCP_VAULT_ROOT="$(pwd)/demo/vault" \
PERSONAVAULT_MCP_SOURCE_PATH=/path/to/your/PersonaVault/checkout \
python -m personavault_mcp.server
```

The service binds to `127.0.0.1:8765` by default, exactly as it does
against a real vault — nothing about the demo vault changes the
loopback-only bind policy or the authentication story.

## How to invoke the two tools

With any MCP Streamable HTTP client, or `scripts/smoke_test.py`'s
pattern:

```json
{"persona": "Rook"}
```

against `get_boot_context` returns Rook's bounded boot context,
including the three approved continuity events.

```json
{
  "persona": "Rook",
  "host_id": "demo-synthetic-host",
  "host_conversation_id": "demo-synthetic-conversation-0001",
  "category": "memory",
  "text": "Now prefers a short written project-status summary at the end of each work week, on Fridays."
}
```

against `propose_session_note` returns `status: "pending_human_review"`
and `review_state: "defer"` — the exact synthetic proposal scenario this
fixture is designed around (see below).

## The intended future demo flow

This fixture is designed so a later slice's simulator can cleanly
demonstrate the full governance loop:

1. A host requests Rook's approved context (`get_boot_context`).
2. PersonaVault returns Rook's bounded context — including the
   already-approved "prefers concise explanations" fact.
3. In the demo conversation, Rook is imagined to newly mention a
   related but different preference: a standing Friday project-status
   summary.
4. The host calls `propose_session_note` with that new fact.
5. The candidate appears as a pending PersonaVault Session Return intake
   — `pending_human_review`, `review_state: "defer"` — durably recorded
   with synthetic host provenance.
6. Approved continuity remains exactly as it was — unchanged — until a
   human reviews and commits that intake **inside PersonaVault itself**.
   (There is no MCP tool to do this, deliberately: see
   "Human review" below.)

This slice does not build the simulator that drives that conversation
end to end — only the fixture it will use.

## Human review (not automated, deliberately)

`propose_session_note` never approves anything — every candidate it
creates lands as PersonaVault's own default `defer` decision, with no
input field that can change that. To actually approve the demo
proposal above (e.g. for a screenshot of "after review"), a human
reviews it the same way any real Session Return intake is reviewed:
open PersonaVault's own desktop app against `demo/vault`, find Rook's
pending intake under Session Return, and approve or reject it there.
PersonaVault-MCP has no commit tool, and this fixture does not add one.

## All resident data is synthetic

Rook is not based on, derived from, or a disguised version of any real
PersonaVault resident. Every fact, preference, and event above is
invented for this fixture and safe to show publicly.
