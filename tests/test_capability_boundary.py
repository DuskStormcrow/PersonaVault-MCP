"""Capability-boundary tests, introduced in Slice 1 and extended in
Slice 2.

These are architecture/governance tests: they prove the adapter's own
source and declared dependencies do not reference PersonaVault
capabilities this design forbids, and do not exhibit background/
autonomous behavior or host-specific terminology.

They do NOT prove that a fully compromised adapter process is incapable
of reaching those capabilities by other means (e.g. dynamically
importing ``personavault`` at runtime, which is possible starting Slice
2, since a real PersonaVault checkout is now importable in this
process). See docs/ARCHITECTURE_CONTRACT_V0_1.md, Correction 1, for why
that distinction matters and what stronger isolation would require.

Slice-2 note: `test_no_personavault_import_anywhere` (Slice 1) has been
replaced by `test_personavault_import_confined_to_approved_modules`
below. Slice 1's version asserted zero PersonaVault coupling anywhere,
which was correct for Slice 1 but is no longer true by design now that
get_boot_context exists — this was anticipated and documented in Slice
1's own contract notes ("that coupling starts in the slice that
implements get_boot_context, not this one"). Every other test in this
file is unchanged from Slice 1 and still passes unmodified.
"""

from __future__ import annotations

import pathlib
import re
import tomllib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "personavault_mcp"


# Slice 3 note: module/class docstrings legitimately need to name a
# forbidden identifier to explain why it's absent (e.g.
# propose_session_note's own docstring explains, in prose, that
# commit_session_intake is "never imported, never called, and never
# reachable from this module" -- that sentence is good governance
# documentation, not a violation). Triple-quoted docstrings are
# therefore stripped before scanning; single-line `#` comments are not,
# since nothing in this package currently needs to write long
# explanatory prose in a line comment, and leaving those scanned keeps
# the check strict for anything shorter and more code-adjacent.
_TRIPLE_QUOTED_STRING = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')


def _all_source_text() -> str:
    chunks = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        chunks.append(_TRIPLE_QUOTED_STRING.sub("", text))
    return "\n".join(chunks)


SOURCE_TEXT = _all_source_text()


# Items 1-4 and 6 from the Slice 1 test requirements, plus a few
# adjacent capabilities the Architecture Contract's deny list also
# names (correction/void, cartridge import/export, persona lifecycle,
# host profile modification) as defense in depth.
DENIED_IDENTIFIER_TOKENS = [
    # 1. canonical commit
    "commit_session_intake",
    "commit_intake",
    # 2. persona identity mutation
    "update_persona",
    # 3. Foundation amendment
    "append_foundation_amendment",
    "foundation_amendment",
    # 4. direct Corelog append
    "append_corelog_entry",
    "corelogstore",
    "corelog.append",
    # correction/void operations
    "correct_session_intake_candidate",
    # cartridge import/export
    "import_cartridge",
    "export_cartridge",
    "import_bundle",
    "export_rehydration_bundle",
    # persona creation/deletion/lifecycle
    "create_persona",
    "retire_persona",
    "archive_persona(",
    "restore_persona",
    # host profile modification
    "hostprofilecatalog",
    # 6. Chronicle/Recall
    "recall",
    "fts5",
    "sqlite3",
    "chronicle_search",
    "semantic_search",
]


@pytest.mark.parametrize("token", DENIED_IDENTIFIER_TOKENS)
def test_denied_identifier_absent_from_source(token: str) -> None:
    assert token.lower() not in SOURCE_TEXT.lower(), (
        f"Forbidden identifier {token!r} found in adapter source. This "
        "adapter must not reference PersonaVault write/mutation/Recall "
        "capabilities without a contract amendment."
    )


# Modules explicitly permitted to import personavault, and required to.
# Adding a module to this set is a design decision (which tool needs
# PersonaVault access), not something to do casually to silence a test.
# Note: tools/get_boot_context.py deliberately does NOT import
# personavault directly -- it goes through personavault_bridge, which is
# the only file that ever does. Keeping this to one file, rather than
# one per tool, is a smaller reviewed surface, not a coincidence.
_MODULES_ALLOWED_TO_IMPORT_PERSONAVAULT = {
    "personavault_bridge.py",
}


def test_personavault_import_confined_to_approved_modules() -> None:
    """Every module in the package is checked individually: modules on
    the allowlist above MUST import personavault (proving the allowlist
    itself stays accurate, not just permissive), and every other module
    MUST NOT — proving PersonaVault coupling stays confined to the
    reviewed surface rather than spreading through the package."""
    forbidden_import_patterns = [
        r"\bimport\s+personavault\b",
        r"\bfrom\s+personavault\b",
    ]
    for path in sorted(SRC_ROOT.rglob("*.py")):
        relative = path.relative_to(SRC_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        has_import = any(re.search(pattern, text) for pattern in forbidden_import_patterns)
        if relative in _MODULES_ALLOWED_TO_IMPORT_PERSONAVAULT:
            assert has_import, (
                f"{relative} is on the PersonaVault-import allowlist but does not "
                "actually import personavault — the allowlist is stale."
            )
        else:
            assert not has_import, (
                f"{relative} imports personavault but is not on the approved "
                "allowlist — PersonaVault coupling must stay confined to "
                "reviewed modules."
            )


# Item 5: no arbitrary filesystem path accepted from a host-facing
# schema. The registry/schema_guard tests exercise this directly; this
# is a static backstop confirming no property named like a path exists
# anywhere a schema might be defined in source.
_PATH_LIKE_PROPERTY_PATTERN = re.compile(
    r'"(?:path|filepath|file_path|filename|dir|directory|root|location)"\s*:',
    re.IGNORECASE,
)


def test_no_path_like_schema_property_in_source() -> None:
    assert not _PATH_LIKE_PROPERTY_PATTERN.search(SOURCE_TEXT), (
        "A schema property that looks like a raw filesystem path was "
        "found in source. No host-facing schema may accept one."
    )


# Item 7: no autonomous loop / scheduler / background agent behavior.
AUTONOMOUS_BEHAVIOR_PATTERNS = [
    r"while\s+True\s*:",
    r"\bschedule\.",
    r"\bBackgroundScheduler\b",
    r"\bapscheduler\b",
    r"\bcelery\b",
    r"\bthreading\.Thread\b",
    r"\.run_forever\(\)",
    r"\bcrontab\b",
]


@pytest.mark.parametrize("pattern", AUTONOMOUS_BEHAVIOR_PATTERNS)
def test_no_autonomous_loop_pattern(pattern: str) -> None:
    assert not re.search(pattern, SOURCE_TEXT), (
        f"Pattern {pattern!r} suggests background/autonomous behavior, "
        "which is out of scope for this adapter at any slice without a "
        "separate governance review."
    )


# Item 10 (Slice 2) / item 17 (Slice 5): no vendor-specific terminology
# in the generic adapter package. Deliberately scoped to
# src/personavault_mcp only — the design-contract doc under docs/ is
# allowed to name real hosts (including Alexa) as context; the
# importable package must stay host/vendor-neutral. Nebius/Nemotron
# added in Slice 5 alongside the transport work, for the same reason.
@pytest.mark.parametrize("brand_token", ["alexa", "amazon", "nebius", "nemotron"])
def test_no_brand_terminology_in_generic_package(brand_token: str) -> None:
    assert brand_token not in SOURCE_TEXT.lower(), (
        f"Brand-specific term {brand_token!r} found in the generic "
        "adapter package. Host-specific material belongs in a future, "
        "separate demo-client layer, never in personavault_mcp itself."
    )


def _pyproject_dependencies() -> list[str]:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return list(data.get("project", {}).get("dependencies", []))


# Item 11 (partial, static half): no dependency on personavault is
# declared, and no scheduler-shaped dependency is declared either. Still
# true as of Slice 5: PersonaVault is reached via the filesystem-path
# bridge (personavault_bridge.py), never a pip dependency, regardless of
# how many other runtime dependencies (mcp, and its own transitive web
# stack) this slice adds.
def test_no_personavault_dependency_declared() -> None:
    deps = " ".join(_pyproject_dependencies()).lower()
    assert "personavault" not in deps, (
        "PersonaVault is reached via personavault_bridge.py's sys.path "
        "mechanism, never a pip dependency — see that module's docstring."
    )


# Item 18 (Slice 5): no public tunnel/remote-hosting dependency added.
# Slice 5 is local-transport-only; Cloudflare Tunnel, ngrok, Tailscale
# Funnel, and cloud-hosting SDKs all belong to later, separately
# authorized work, if ever.
@pytest.mark.parametrize(
    "forbidden_dependency",
    ["ngrok", "cloudflared", "pyngrok", "tailscale", "boto3", "google-cloud", "azure-"],
)
def test_no_tunnel_or_cloud_hosting_dependency_declared(forbidden_dependency: str) -> None:
    deps = " ".join(_pyproject_dependencies()).lower()
    assert forbidden_dependency not in deps, (
        f"{forbidden_dependency!r}-shaped dependency found. Public tunneling and "
        "cloud hosting are explicitly out of scope for this slice."
    )


def test_no_scheduler_dependency_declared() -> None:
    deps = " ".join(_pyproject_dependencies()).lower()
    for banned in ("apscheduler", "celery", "schedule"):
        assert banned not in deps, f"{banned!r} must not be a declared dependency in Slice 1."
