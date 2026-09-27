"""A non-canonical, in-process cache correlating a host's own conversation
identity with a PersonaVault Session Return ``session_id``.

This exists because PersonaVault Core currently has no durable, queryable
field recording "which host conversation does this returned session
belong to" (see the Slice 3 report for the precise, NOT-YET-IMPLEMENTED
proposed additive schema change that would add one). Until/unless that
change is made, reusing the same PersonaVault session across multiple
proposals from the same host conversation is only possible within a
single adapter process's lifetime -- this cache is exactly that, no more.

Explicitly NOT canonical:
- it is never written to disk;
- it is lost on adapter restart or crash;
- PersonaVault itself has no way to rediscover this mapping without it,
  which is a disclosed limitation of proceeding without the Core change,
  not a hidden one.

A cache miss (including after a restart) simply causes the next proposal
for what a host considers "the same conversation" to open a new
PersonaVault session via ``create_returned_session`` -- safe, if slightly
wasteful (the earlier session becomes an orphan with no intake attached,
which is itself a legitimate, inspectable, recoverable state, not
corruption).
"""

from __future__ import annotations

CorrelationKey = tuple[str, str, str]


class SessionCorrelationCache:
    """Keyed by ``(persona, host_id, host_conversation_id)`` -- the raw
    input strings a host supplied, not a resolved PersonaVault
    ``persona_id``, since resolution only happens after a cache lookup
    would already need to have occurred. Two different aliases for the
    same persona (e.g. folder name vs. display name) are therefore
    treated as different cache keys; both still produce valid, correctly
    attributed PersonaVault sessions, so this is a minor cache-efficiency
    limitation, not a correctness one.
    """

    def __init__(self) -> None:
        self._map: dict[CorrelationKey, str] = {}

    def get(self, persona: str, host_id: str, host_conversation_id: str) -> str | None:
        return self._map.get((persona, host_id, host_conversation_id))

    def put(self, persona: str, host_id: str, host_conversation_id: str, session_id: str) -> None:
        self._map[(persona, host_id, host_conversation_id)] = session_id

    def clear(self) -> None:
        """Test-only helper, mirroring registry.reset_registry_for_tests."""
        self._map.clear()
