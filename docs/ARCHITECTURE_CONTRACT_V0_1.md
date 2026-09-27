# PersonaVault MCP Adapter — Architecture Contract v0.1 (corrected)

Status: approved with two corrections (this revision). Slice 1 (adapter
skeleton + capability-boundary tests) authorized and implemented against
this corrected contract.

This document supersedes the original v0.1 draft. Two corrections are
applied inline below, at the sections they affect, rather than kept as a
separate errata list — so the contract reads correctly on its own from
this point forward. A short changelog is kept at the end for traceability.

---

## 1. Architectural boundary

```
PersonaVault Core (personavault/*)
   - owns identity, Corelog, Session Return lifecycle, Host Trips, cartridges
   - zero network code today
   - stays exactly this way

        │  in-process Python calls only (Vault(root) as a library import)
        ▼

PersonaVault MCP Adapter  ← sibling, separate process & repo
   - the only thing that imports personavault as a dependency
   - the only thing that speaks MCP / Streamable HTTP
   - exposes exactly two tools (§2) and nothing else reachable through
     its designed and tested surface

        │  MCP protocol (Streamable HTTP, spec 2025-11-25+)
        ▼

Hosts (Alexa+ simulated client today; Claude/ChatGPT/Codex/local models later)
```

PersonaVault remains canonical for identity, approved continuity,
Corelog/Chronicle records, human-reviewed changes, Host Trip/Session
Return lifecycle, provenance, and governance. The adapter is only a
controlled access door — it holds no canonical data of its own.

### Correction 1 — what this boundary does and does not guarantee

The original draft stated that even a fully compromised adapter process
could reach nothing beyond the small set of PersonaVault methods it
imports. **That claim is too strong and is withdrawn.**

**What the v0.1 design DOES guarantee:**
The adapter's *designed and tested* MCP capability surface — its tool
registry, its input/output schemas, and its own source — exposes only
the explicitly approved PersonaVault operations. Static imports,
dispatch tables, schemas, and the tests in `tests/` prevent *accidental*
capability creep during normal development: a developer cannot casually
add a call to `commit_session_intake` without an explicit test failing
and a deliberate contract amendment.

**What it DOES NOT guarantee:**
This is not an operating-system or process-level sandbox. If the full
`personavault` package is installed and importable inside the adapter's
Python environment (which it will be, starting the slice that
implements `get_boot_context`), a **fully compromised** adapter process
— one already running arbitrary attacker-controlled code, for whatever
reason — could call `importlib.import_module("personavault.storage")`
and reach anything in it, regardless of what the adapter's own source
was ever written to import. The import-boundary tests are
**architecture/governance tests**: they prove intent and catch
accidental drift during ordinary development and review. They are not
proof of hostile-process containment, and this document must never be
read as claiming otherwise.

**If stronger isolation is ever required**, that is a separate security
design, out of scope for v0.1, and could look like:
- a narrow local IPC boundary between two processes, where the callable
  surface is enforced by what the IPC channel itself carries, not by
  what's importable in the calling process;
- a separately constrained PersonaVault service process exposing only a
  minimal RPC surface, run under a different OS user/permission set than
  the adapter;
- OS/process sandboxing (containers, seccomp, restricted service
  accounts);
- or another real isolation mechanism with its own threat model.

None of this is needed for Slice 1, which carries no dependency on
`personavault` at all yet (§ Slice 1 notes, below) — the distinction
above becomes materially relevant starting the slice that adds that
dependency, and should be re-read in full before that slice begins.

---

## 2. Initial tool surface

*(Unchanged from the approved draft except for Correction 2, applied to
the provenance-related field below. Full tool contracts — input/output
schemas, error states, persona selection behavior — are retained as
previously approved and are not re-implemented in Slice 1.)*

### Tool A — `get_boot_context`
Wraps `Vault.boot_package_preview()` verbatim; returns a bounded subset;
the 5-approved-event limit stays intact; never returns raw Corelog,
checksum, or asset-status fields.

### Tool B — `propose_session_note`
Wraps `create_returned_session()` → `save_session_intake()`; never calls
`commit_session_intake`; never exposes a `decision` field in its input
schema, so every proposal lands as `defer` regardless of what a host
requests.

**Input schema** (corrected):
```json
{
  "persona": "string, required",
  "host_id": "string, required — host-neutral identifier the caller declares itself as",
  "host_conversation_id": "string, required — the host's own conversation/session identifier, opaque to PersonaVault",
  "category": "enum, required — one of memory | project_update | relationship_development | development_signal | recognition_fidelity_note | session_only_note",
  "text": "string, required",
  "source_excerpt": "string, optional"
}
```
This was already correctly modeled as a distinct field at the MCP tool
boundary in the original draft. Correction 2 (below) fixes where this
value goes *inside PersonaVault's own storage*, which the original draft
got wrong.

---

## 3. Explicitly inaccessible PersonaVault capabilities (deny-by-design)

Unchanged list (commit, persona update, Foundation amendment, direct
Corelog append, correction/void, cartridge import/export, persona
lifecycle, host profile modification, Library root changes, direct file
access, Chronicle/Recall, Stage Three/autonomous behavior) — see the
previously approved table for the full mapping of capability → why it's
absent.

**Correction 1 applies here too.** Read "how tests can prove these
methods are unreachable" as: *tests prove these methods are not part of
the adapter's own designed call surface*, not as *tests prove a
compromised process cannot reach them by any means*. The three-level
test strategy (static import test, attribute-absence test, behavioral
smuggling test) is retained exactly as designed — it is good, real,
valuable engineering — just not over-claimed as containment.

---

## 4. Provenance contract

### Correction 2 — `host_conversation_id` is its own field, not an overload of `host_model`

The original draft recommended repurposing the PersonaVault session
record's existing `host_model` field to carry the host's conversation
identifier. **This is withdrawn.** `host_model` means "which model the
host is running" (e.g. `"nova-3"`, `"claude-opus-5"`) and must keep
meaning exactly that. A conversation/session identifier is a different
concept and deserves its own, explicitly named field — provenance must
stay interpretable years later without requiring knowledge of a
temporary convention that happened to reuse an unrelated field.

**Recommendation**: add one new, explicitly named field,
`host_conversation_id`, to the `session_return.v0.1` session record
schema (alongside the existing `host_platform`/`host_model`/
`source_artifact` fields), as an additive, optional field — old readers
that don't know about it can simply ignore it, consistent with
PersonaVault's own existing migration doctrine of additive, non-breaking
schema growth.

**This is a PersonaVault Core change, not an adapter-only change.** It
is explicitly **not part of Slice 1** (Slice 1 has no PersonaVault
dependency at all) and not part of the tool implementation slices either
— it belongs to the provenance-wiring slice (see Implementation Slices,
step 4), and should be raised to Stormcrow/Nyx as its own small, reviewed
PersonaVault Core change *before* that slice writes any adapter code
that depends on it. This is the one place in the whole adapter design
that touches PersonaVault Core, and it should be treated with the same
weight as any other PersonaVault Core schema change — not smuggled in as
an adapter implementation detail.

**Restated, corrected provenance mapping:**

| Question | Answered by |
|---|---|
| Which host proposed this? | `host_platform` = adapter-supplied `host_id` (host-neutral) |
| Which model is the host running? | `host_model`, meaning only that, unchanged |
| Which host conversation/session did it come from? | **new field**: `host_conversation_id` (session-record level; requires the PersonaVault Core change above) |
| Which adapter version handled it? | `candidate["created_by"]` = `"personavault-mcp-adapter/<semver>"` |
| Which MCP tool produced it? | `source_artifact`, e.g. `"mcp:propose_session_note"` |
| When was it received? | `created_at` (already automatic) |
| Was it synthetic/demo data? | config-level guarantee: the demo adapter instance points at a dedicated demo vault root, never the real one — not a data flag |
| Was it approved/rejected/deferred/session-only? | native `decision` field + `commit_session_intake`'s own event types |
| Did a human perform the canonical commit? | provable by capability absence (§3), not by a field |

Everything else in the provenance contract (the optional `source`
enum-value extension to `"mcp_proposal"`) is unchanged from the
originally approved draft.

---

## 5–14

Unchanged from the originally approved draft (transport contract,
authentication boundary, synthetic demo persona, simulated Alexa+
boundary, error semantics, security/privacy tests, repository/package
layout, versioning, future extension points, roadmap discipline). Not
reproduced again here to avoid drift between two copies of the same
text; this document and the previously approved chat record together
constitute the full contract. If a future revision needs to touch any of
§5–14, it should be folded into this file directly, the same way these
two corrections were.

---

## Slice 1 notes (this revision)

Slice 1 (adapter skeleton + capability-boundary tests) was implemented
against this corrected contract with the following properties:

- Zero dependency on the `personavault` package — deliberately, so that
  the "does not guarantee hostile-process containment" caveat in
  Correction 1 is moot in practice for this slice: there is nothing
  installed in this process for a compromised instance to reach.
- The tool registry (`personavault_mcp.registry.TOOL_REGISTRY`) is
  empty. `APPROVED_TOOL_NAMES` reserves `get_boot_context` and
  `propose_session_note` as the only names any future registration may
  use.
- No transport, no networking, no authentication is wired up. A config
  skeleton (`personavault_mcp.config.AdapterConfig`) exists with
  loopback-only defaults, unused by anything yet.
- No Alexa/Amazon terminology appears anywhere in
  `src/personavault_mcp` (enforced by test); this document is the
  appropriate place for that context, not the package.

---

## Slice 2 notes

Slice 2 (`get_boot_context`, the adapter's first functional tool) was
implemented against this contract with the following properties and one
discovered constraint:

- **PersonaVault has no packaging metadata.** Checked directly:
  `pip install -e <PersonaVault checkout>` fails with "does not appear to
  be a Python project" — there is no `setup.py`/`pyproject.toml`/
  `setup.cfg` at PersonaVault Core's root. This is not "genuinely
  impossible without a Core change" (a Core-free alternative exists), so
  Slice 2 did not stop and ask — it used a filesystem-path bridge
  (`personavault_bridge.py`) instead: PersonaVault's checkout is added to
  `sys.path` at call time, pinned to a recorded commit
  (`f9712aceda1912c6e5913bb4b29fc28ed4408933`), never vendored. No pip
  dependency on `personavault` was added anywhere in this repo.
  Recommendation, not performed: PersonaVault Core adding standard
  packaging metadata would let a future slice replace this bridge with an
  ordinary pinned dependency — that is a separate, future, reviewed Core
  change.
- **PersonaVault coupling is confined to one file.** Only
  `personavault_bridge.py` imports `personavault`; `tools/get_boot_context.py`
  goes through the bridge's own functions, not a direct import. Proven by
  test (`test_personavault_import_confined_to_approved_modules`).
- **Output is allowlisted, not passed through.** `get_boot_context`
  constructs its own output dict field-by-field from
  `boot_package_preview()`'s allowed fields; the six known private fields
  (`corelog_status`, `asset_status`, `checksum_status`, `state_status`,
  `origin`, `preview_text`) are verified absent from the tool's output by
  test, cross-checked against the real underlying call to confirm they
  do exist on the source side and are being deliberately dropped.
  All ten allowed field names were verified against the real
  `boot_package_preview()` return dict with zero renaming needed — no
  field-name mapping was required.
- **The 5-event limit is inherited, not hardcoded.** The tool truncates
  to whatever `approved_continuity_limit` PersonaVault itself reports,
  rather than hardcoding `5` independently — if
  `APPROVED_CONTINUITY_PREVIEW_LIMIT` changes in PersonaVault Core, this
  tool's behavior updates automatically with it.
- **Not registered on import.** `import personavault_mcp` still performs
  no side effects; `personavault_mcp.bootstrap.register_default_tools()`
  must be called explicitly, and registers exactly one tool.

Nothing discovered in Slice 2 weakens the contract or changes the
planned Slice 3 (`propose_session_note`) design — the packaging-metadata
gap is a mild inconvenience worked around cleanly, not a structural
problem. It does mean Slice 3's own dependency section should note the
same bridge mechanism rather than assume a pip dependency will exist by
then.

## Slice 3 notes

Slice 3 (`propose_session_note`, the adapter's first write-adjacent
tool) was implemented against this contract. It surfaced two genuine
PersonaVault Core findings and confirmed one design refinement; none of
them were addressed by modifying Core, and none weaken the boundary this
contract exists to protect.

**Session/intake mapping, verified against the real API (not assumed):**
`Vault._write_intake_record` overwrites its target file wholesale, and
the only read-back method (`Vault._load_intake_record`) is private.
Calling `save_session_intake` twice with the same `intake_id` but only a
new candidate would silently discard whatever was previously proposed
and unreviewed. The safe mapping actually implemented: **one host
conversation → one PersonaVault session** (created once via
`create_returned_session`, reused via an in-process correlation cache),
and **each individual proposal call → its own new intake** (a fresh
PersonaVault-generated `intake_id`, one candidate), all sharing that
session_id. PersonaVault's schema never required a 1:1 session:intake
relationship; this is the one mapping the public API supports without
risking data loss or reaching into private methods — not a workaround.

**Verified duplicate behavior:** PersonaVault's own duplicate protection
(`Vault._committed_candidate_keys`) is scoped to `(event_type,
intake_id, candidate_id)` at **commit** time only. Since this tool never
commits and always creates a fresh `intake_id` per proposal,
**repeated identical proposals are not deduplicated** — each becomes an
independent, separately reviewable pending candidate. This is disclosed,
tested behavior, not an oversight; per the slice's own instruction,
no separate dedup database was invented to paper over it.

**Two additive PersonaVault Core changes are recommended, NOT
implemented — for separate Stormcrow/Nyx review before any future slice
depends on them:**

1. **Add `host_conversation_id` to `session_return.v0.1`.** Checked
   against every existing session-record field
   (`host_platform`, `host_model`, `source_artifact`, `notes`, `source`):
   none is semantically correct for "which host conversation this came
   from" (this is exactly the mistake Correction 2 already flagged once;
   it was not repeated here). Proposed: a new optional field,
   `host_conversation_id: str = ""`, plus accepting it as an optional
   keyword argument on `create_returned_session`. Additive, backward
   compatible, no existing record needs to change.
2. **Make `source` an accepted parameter on `create_returned_session`.**
   Currently hardcoded inside the method to the literal string
   `"manual_user_entry"` regardless of caller — there is no way to pass
   a different value today. Proposed: `source: str = "manual_user_entry"`
   as a real keyword argument, so a future slice could pass
   `source="mcp_proposal"` and make MCP-originated sessions distinguishable
   from manual ones by a validated field rather than by convention alone.

**Until either change is made:** `propose_session_note` uses
`host_platform` for `host_id` (a correct, pre-existing fit — not an
overload) and leaves `host_conversation_id` living only in the adapter's
own in-process, non-canonical cache (`session_correlation.py`). Honestly
disclosed consequence: **after an adapter restart, PersonaVault has no
way to rediscover which existing session a given host conversation
belongs to** — the next proposal for what a host considers "the same
conversation" opens a new session, and the earlier one becomes an
orphan (a session record with no intake ever attached) — itself a
legitimate, human-inspectable state, not corruption, but a real,
disclosed limitation of proceeding without the Core change.

**A separate, real PersonaVault Core issue was found and worked around
at the adapter's door (not fixed in Core):** `Vault._resolve_persona_dir`
joins `name_or_folder` onto its base directory with plain
`Path.__truediv__`. Pathlib's own join semantics treat an absolute
`name_or_folder` as a full replacement, not an append — so
`persona="/etc/passwd"` resolved to the real file `/etc/passwd` on the
host running the tests. `load_persona` happens to fail safely (a
pre-existing `.exists()` check swallows the resulting `OSError`);
`create_returned_session` does not (it raised an uncaught
`NotADirectoryError` from inside PersonaVault Core, verified directly in
`tests/test_propose_session_note.py::test_personavault_core_resolve_persona_dir_absolute_path_finding`).
Both `get_boot_context` and `propose_session_note` now reject any
path-shaped `persona` input at the door
(`persona_name_guard.py`), before PersonaVault ever sees it — this
counted as a "genuine shared infrastructure defect," which Slice 3's own
authorization explicitly permitted fixing even though it touches Slice
2's file. **Proposed, not-yet-implemented Core fix:** have
`_resolve_persona_dir` reject an absolute `name_or_folder` outright
(e.g. `if Path(name_or_folder).is_absolute(): raise
FileNotFoundError(...)`), which would close this at the source for every
current and future caller, not just the two tools this adapter happens
to expose.

None of the above requires revising the sections of this contract
concerning the deny-by-design capability list, the transport, or the
authentication boundary — they are refinements to the provenance and
session-mapping sections (§2, §4) and one new, narrowly-scoped shared
module (`persona_name_guard.py`), not a change in kind.

## Slice 4 notes

Slice 4 (provenance hardening) consumed the PersonaVault Core Maintenance
Gate (Core commit `d8b9762cf3371572383b72336cd1ad23f91f8dea`) and closed
one of the two limitations Slice 3 disclosed, while confirming the other
remains genuinely open.

**Durable provenance — now real.** `propose_session_note` now calls
`create_returned_session` with `host_platform=host_id`,
`host_conversation_id=host_conversation_id`, and
`source="mcp_proposal"`. All three are native PersonaVault fields as of
the Maintenance Gate — none repurposed, none invented. Which host, which
host conversation, and that a session came via MCP (rather than manual
desktop entry, which keeps PersonaVault's own default,
`"manual_user_entry"`, completely unaffected) are now readable back from
PersonaVault alone, indefinitely, with no dependency on the adapter's
own memory. `mcp_proposal` was chosen to match the `source` field's own
existing precedent (a single snake_case value, `"manual_user_entry"`) —
checked against every other "source"/"created_by" value already in
PersonaVault (retirement, corelog, portrait-library code all use a
different, phrase-style convention for unrelated fields), and none of
them is a better fit for this specific field.

**Durable correlation — still open, verified not just assumed.**
Every public method on `Vault` was enumerated: `create_returned_session`,
`save_session_intake`, `commit_session_intake`, and
`correct_session_intake_candidate` are the only public Session Return
methods, and all four are write-shaped or require an already-known
`session_id`. There is no public method to list or search returned
sessions by persona, host, or `host_conversation_id` — the one read
method (`Vault._load_session_record`) is private, and this project's own
rule is not to reach into private methods merely to avoid a cache. The
adapter's in-process `SessionCorrelationCache` therefore remains, by
verified necessity. Its consequence is now much smaller than before this
slice: only the *correlation* is lost on adapter restart, never the
underlying data — a repeated host conversation after a restart opens a
second, independent, but equally durable and correctly-provenanced
session, rather than resuming the first. Both sessions remain fully
inspectable by a human reviewing PersonaVault directly.

**Recommended, not implemented**: a small, additive, read-only public
method — something in the shape of `Vault.list_returned_sessions(name_or_folder,
status="active") -> list[dict]`, reading `Chronicle/sessions/*.json` for
one persona — would let a future slice close the correlation gap too,
by searching for an existing session whose `host_platform`/
`host_conversation_id` match before creating a new one. This is a
PersonaVault Core change and was not made in this slice; it is a
candidate for a future, separately reviewed maintenance pass, not an
urgent blocker (the current behavior is safe, just occasionally
duplicative).

No governance boundary changed: `commit_session_intake` remains
unimported, no input field can produce an approval, and every
`get_boot_context` guarantee is untouched (that file was not modified
this slice). Tool count remains exactly two.

## Slice 5 notes

Slice 5 turned the adapter from a tested library into an actual, locally
reachable MCP service, without changing anything about §1-§4's boundary.

**MCP library**: the official `mcp` Python SDK, pinned `mcp>=1.30.0,<2`.
Checked directly against the installed package (not assumed): 1.30.0's
`mcp.types.LATEST_PROTOCOL_VERSION` is exactly `"2025-11-25"` — this
project's target spec level, an exact match rather than "later,
presumably compatible" (the 2.x line's `LATEST_PROTOCOL_VERSION` is a
later date, `2026-07-28`). 1.x also keeps the classic `FastMCP` name and,
critically, the low-level `Server.list_tools()`/`Server.call_tool()`
decorator API — verified that mcp 2.x's high-level `MCPServer.add_tool`
has no parameter anywhere to supply an explicit JSON schema; it only
infers one from a Python function's type hints, which risked silently
diverging from this adapter's hand-built, strict schemas
(`additionalProperties: false`, enums sourced from PersonaVault's own
constants). `server.py` uses `FastMCP` only for its tested Streamable
HTTP serving machinery, and registers tools via its underlying low-level
`Server` (`app._mcp_server`) with our own verbatim schemas — verified
that a fresh `FastMCP` instance advertises zero tools/resources/prompts
until something is explicitly added, so nothing from the framework is
exposed outside our own registry.

**Streamable HTTP**: implemented via `FastMCP.run(transport="streamable-http")`
(and, for tests, `FastMCP.streamable_http_app()` served under a real
`uvicorn.Server`). Confirmed working end to end against a real `mcp`
client, including protocol version negotiation logging
`Negotiated protocol version: 2025-11-25` in the manual smoke test.

**Bind policy**: `config.LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}`;
`assert_bind_policy_is_safe` rejects `build_app`/startup outright for
any other `bind_host`, including `"0.0.0.0"` — option 1 from the
authorization ("reject startup entirely"), not a token-auth mode. No
authentication is implemented or required for this loopback-only
default; the enforced bind policy is what makes that acceptable, not an
assumption. A future, separately authorized slice would need to add its
own explicit non-loopback + auth mode; this one refuses to start rather
than permit it.

**Tool exposure**: `list_tools()`/`call_tool()` dispatch entirely
through the existing `registry.TOOL_REGISTRY` (populated by
`bootstrap.register_default_tools()`), never duplicating tool logic in
the transport layer. Every adapter error (`BootContextError`,
`ProposeSessionNoteError` subclasses) is converted to a
`CallToolResult(isError=True, content=[TextContent(f"{code}: {message}")])`
via one function (`_error_result`); a truly unexpected exception is
caught separately and never has its own message exposed to the client.
`jsonschema.validate` (via `call_tool(validate_input=True)`) enforces
our exact schema at the transport boundary before a handler ever runs,
verified directly by reading the installed library's source — a real
additional layer, not a claim.

**Logging**: `personavault_mcp.server`'s own logger records only tool
names, success/failure codes, and start/stop — verified directly (not
assumed) that neither proposal text nor boot-context contents ever
appear in it, via an integration test that captures real log output
during a real call. The `mcp` client SDK's own debug logging (a
different, caller-side concern) does log its own outgoing payloads at
DEBUG level; that is the caller's own trace of what it sent, not
something a server-side deployment would see or that this adapter
controls.

**No health endpoint added.** Optional per the authorization; skipped to
keep the surface minimal. Nothing prevents adding a plain Starlette
route returning `{"status": "ok"}` later without difficulty.

**Known limitations carried forward, unchanged by this slice**: the
Slice 4 correlation-cache limitation (no durable rediscovery of a host
conversation's session after an adapter restart) is unaffected — this
slice is transport, not correlation. Non-loopback/remote operation,
real authentication beyond "none, because it can't reach anything but
loopback," and any demo/simulator client remain for later, separately
authorized work.

## Changelog

- **v0.1 (original)** — approved with two corrections requested.
- **v0.1 (revision 1)** — Correction 1 (import discipline is not a
  process sandbox) applied to §1 and §3. Correction 2 (`host_conversation_id`
  as its own field, not an overload of `host_model`) applied to §2 and
  §4, with the required PersonaVault Core schema change flagged as a
  pre-requisite for the provenance-wiring slice, not folded into Slice 1.
- **v0.1 (revision 2, Slice 2)** — added Slice 2 notes above: PersonaVault
  packaging-metadata gap and the filesystem-path bridge adopted to work
  around it without a Core change.
- **v0.1 (revision 3, Slice 3)** — added Slice 3 notes above: the
  verified one-session/many-intakes mapping, verified (non-)duplicate
  behavior, two proposed-but-not-implemented additive Core changes
  (`host_conversation_id` field; a real `source` parameter on
  `create_returned_session`), and a documented PersonaVault Core
  absolute-path finding in `_resolve_persona_dir`, worked around in
  `persona_name_guard.py` for both tools.
- **v0.1 (revision 4, Slice 4)** — both Slice 3 Core proposals were
  implemented in a separate PersonaVault Core Maintenance Gate
  (`d8b9762cf3371572383b72336cd1ad23f91f8dea`) and are now used by
  `propose_session_note`: durable `host_conversation_id` and a real
  `source="mcp_proposal"`. Durable provenance is resolved; durable
  correlation remains open (verified no public Core lookup API exists)
  and is recommended, not implemented, as a small future read-only
  method. The absolute-path finding is fixed at the Core level too;
  `persona_name_guard.py` remains as intentional defense-in-depth.
- **v0.1 (revision 5, Slice 5)** — added Slice 5 notes above: real
  Streamable HTTP transport (`mcp>=1.30.0,<2`, spec `2025-11-25` exact
  match), loopback-only bind policy enforced at startup, no auth for
  that loopback-only mode, tool exposure dispatched through the
  existing registry with unmodified schemas, and verified log-content
  safety. `PersonaVault-MCP` is now a runnable local MCP service.
