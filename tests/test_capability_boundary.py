"""Slice 1 capability-boundary tests.

These are architecture/governance tests: they prove the adapter's own
source and declared dependencies do not reference PersonaVault
capabilities this design forbids, and do not exhibit background/
autonomous behavior or host-specific terminology.

They do NOT prove that a fully compromised adapter process is incapable
of reaching those capabilities by other means (e.g. dynamically
importing ``personavault`` at runtime if it happens to be installed in
the same environment). See docs/ARCHITECTURE_CONTRACT_V0_1.md,
Correction 1, for why that distinction matters and what stronger
isolation would require. Slice 1 also carries no dependency on
``personavault`` at all, so at this stage the distinction is moot in
practice — there is nothing installed to reach.
"""

from __future__ import annotations

import pathlib
import re
import tomllib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "personavault_mcp"


def _all_source_text() -> str:
    chunks = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        chunks.append(path.read_text(encoding="utf-8"))
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


def test_no_personavault_import_anywhere() -> None:
    """Slice 1 has zero functional coupling to PersonaVault — no tool
    imports it, so none of the denied capabilities above are reachable
    even in principle through this package's own code paths (though see
    the module docstring: this is not a claim about process isolation)."""
    forbidden_import_patterns = [
        r"\bimport\s+personavault\b",
        r"\bfrom\s+personavault\b",
    ]
    for pattern in forbidden_import_patterns:
        assert not re.search(pattern, SOURCE_TEXT), (
            "personavault must not be imported anywhere in Slice 1 — no "
            "functional tool exists yet that needs it."
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


# Item 10: no Amazon/Alexa terminology in the generic adapter package.
# Deliberately scoped to src/personavault_mcp only — the design-contract
# doc under docs/ is allowed to name real hosts (including Alexa) as
# context; the importable package must stay host-neutral.
@pytest.mark.parametrize("brand_token", ["alexa", "amazon"])
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
# declared yet, and no scheduler-shaped dependency is declared either.
def test_no_personavault_dependency_declared() -> None:
    deps = " ".join(_pyproject_dependencies()).lower()
    assert "personavault" not in deps, (
        "Slice 1 introduces no dependency on the personavault package "
        "itself — that coupling starts in the slice that implements "
        "get_boot_context, not this one."
    )


def test_no_scheduler_dependency_declared() -> None:
    deps = " ".join(_pyproject_dependencies()).lower()
    for banned in ("apscheduler", "celery", "schedule"):
        assert banned not in deps, f"{banned!r} must not be a declared dependency in Slice 1."
