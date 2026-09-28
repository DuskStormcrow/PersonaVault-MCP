"""The synthetic demo resident's own content -- data only, no logic.

Kept separate from ``build_demo_vault.py`` so tests can import and check
this content directly (e.g. "no real resident name appears anywhere in
here") without needing to run the builder or touch a filesystem.

Everything below is fictional. ``Rook`` is generated entirely from
PersonaVault Core's own generic, stock "No-Nonsense Work Partner" guided-
creation recipe (``personavault.guided_creation``) -- the same recipe
any real user could pick from the ordinary guided-creation flow. No
field here was copied, adapted, anonymized, or lightly disguised from
any actual PersonaVault resident. ``REAL_RESIDENT_NAMES_NEVER_TO_USE``
documents that constraint and is itself checked by
``tests/test_demo_fixture.py`` against every string in this module.
"""

from __future__ import annotations

# Real PersonaVault residents this fixture must never resemble, copy,
# anonymize, or lightly disguise. Named explicitly (not inferred) so a
# test can grep this fixture's own content for them. Add to this tuple,
# never remove from it, if another real resident is ever introduced.
REAL_RESIDENT_NAMES_NEVER_TO_USE: tuple[str, ...] = (
    "Nyx",
    "Vesper",
    "Eve",
    "Mia",
    "Stormcrow",
)

# --- The synthetic resident itself ------------------------------------------

DEMO_PERSONA_NAME = "Rook"

# One of PersonaVault Core's own five built-in guided-creation starter
# recipes (personavault/guided_creation.py:STARTER_RECIPES) -- entirely
# stock content, not authored for this fixture. Chosen because its
# "task_project_memory" mode and practical, work-focused framing fit the
# demo proposal scenario below (a weekly project-status preference)
# better than the other four recipes.
DEMO_RECIPE_ID = "no_nonsense_work_partner"

# --- Approved continuity seeded before any demo conversation happens -------
#
# Exactly three items -- within the "3-5" range the Slice 6 brief asks
# for, and no more: this is a product demonstration fixture, not a
# novel. Categories match personavault.storage.SESSION_CANDIDATE_CATEGORIES
# (see propose_session_note.py's own CANDIDATE_CATEGORIES, verified
# identical). Each is durably created via the same real Session Return
# intake + human-review-equivalent commit path a real reviewer's approval
# would use (Vault.create_returned_session -> save_session_intake ->
# commit_session_intake) -- not written directly into PersonaVault's
# storage format, so it stays a faithful example of what "already
# approved continuity" really looks like on disk.
#
# The first item (a preference) is also the one the demo proposal
# scenario below is designed to sit alongside: Rook already prefers
# concise explanations; the demo conversation has them state a *new*,
# different preference (weekly Friday summaries), which a host proposes
# and a human has not yet reviewed.
APPROVED_CONTINUITY_SEED: tuple[dict[str, str], ...] = (
    {
        "category": "memory",
        "text": "Prefers concise, technical explanations over long narrative answers.",
    },
    {
        "category": "project_update",
        "text": (
            "Completed the initial project inventory for the sample "
            "\"Northgate\" workspace, with no blocking issues found."
        ),
    },
    {
        "category": "relationship_development",
        "text": (
            "Works with the user primarily during weekday mornings and "
            "appreciates a short status update before diving into new requests."
        ),
    },
)

# The host_platform/source recorded for the seeding session above --
# never "mcp_proposal" (this data was not proposed by an MCP host; it was
# seeded directly by the fixture builder, and says so truthfully).
DEMO_SEED_HOST_PLATFORM = "demo-fixture-builder"
DEMO_SEED_SOURCE = "demo_fixture_seed"
DEMO_SEED_REVIEWER = "demo-fixture-builder"

# --- The demo proposal scenario (for Slice 6 MCP verification, and for --
# --- Slice 7's future simulator to reenact) ---------------------------------
#
# During a demo host conversation, Rook is imagined to newly state a
# preference that is NOT yet part of approved continuity: a weekly,
# Friday, written project-status summary. This is deliberately in the
# same category ("memory", a preference) as the first seeded item above,
# so the demo story reads cleanly: "Rook already prefers concise
# explanations; today they also mentioned wanting a standing Friday
# summary" -- plausible, easy to understand, clearly new, and harmless.
#
# host_id/host_conversation_id are both obviously synthetic and
# host-neutral -- no vendor or product name, consistent with this slice
# not building any simulated external host client yet.
DEMO_PROPOSAL_HOST_ID = "demo-synthetic-host"
DEMO_PROPOSAL_HOST_CONVERSATION_ID = "demo-synthetic-conversation-0001"
DEMO_PROPOSAL_CATEGORY = "memory"
DEMO_PROPOSAL_TEXT = (
    "Now prefers a short written project-status summary at the end of "
    "each work week, on Fridays."
)
