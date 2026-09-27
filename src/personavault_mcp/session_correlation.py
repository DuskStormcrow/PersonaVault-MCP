"""A non-canonical, in-process cache correlating a host's own conversation
identity with a PersonaVault Session Return ``session_id``.

Status as of Slice 4 (PersonaVault Core commit
d8b9762cf3371572383b72336cd1ad23f91f8dea): the underlying *provenance*
gap this cache originally stood in for is closed -- PersonaVault now
durably stores ``host_conversation_id`` on the session record itself, so
which host conversation produced a given session is readable back from
PersonaVault alone, indefinitely, surviving any adapter restart.

What is NOT closed, and is the reason this cache still exists: PersonaVault
has no public method to *look up* a session by persona, host, or
host_conversation_id -- only to create one, or to act on one whose
session_id is already known. Verified directly against ``Vault`` (every
public method was enumerated): ``create_returned_session`` (write),
``save_session_intake`` (write, requires an already-known session_id),
``commit_session_intake`` (write), ``correct_session_intake_candidate``
(write). The one read method that exists, ``_load_session_record``, is
private, and this project's own rule is not to reach into private
PersonaVault methods merely to avoid a cache. So: durable provenance is
now real; durable *correlation* is not yet possible without a new,
small, public Core query method -- proposed but not implemented (see the
Slice 4 report) -- and this cache remains, by verified necessity, to
provide it for the lifetime of one adapter process.

Explicitly NOT canonical:
- it is never written to disk;
- it is lost on adapter restart or crash;
- without a future Core lookup method, PersonaVault has no way to
  rediscover this specific mapping on its own.

A cache miss (including after a restart) simply causes the next proposal
for what a host considers "the same conversation" to open a new
PersonaVault session via ``create_returned_session`` -- safe, if slightly
wasteful (the earlier session becomes an orphan with no intake attached,
which is itself a legitimate, inspectable, recoverable state, not
corruption). Every prior session and its proposals remain fully intact
and durably provenanced on disk regardless -- only the *correlation* to
a newly-restarted adapter process is lost, never the underlying data.
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
