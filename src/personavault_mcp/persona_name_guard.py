"""Rejects a persona-name input that looks like a filesystem path.

Discovered during Slice 3 (verified concretely, not assumed): PersonaVault
Core's own ``Vault._resolve_persona_dir`` joins ``name_or_folder`` onto a
base directory using plain ``Path.__truediv__``. Pathlib's own documented
join semantics silently treat an absolute ``name_or_folder`` as a full
replacement of the base path, not an append -- so
``persona="/etc/passwd"`` reaches ``_resolve_persona_dir`` and resolves to
``Path("/etc/passwd")``, a real file on this host, as though it were a
resolved persona directory, because ``base_dir / "/etc/passwd"`` equals
``Path("/etc/passwd")`` and that path exists.

What happens next depends entirely on which PersonaVault method is
called afterwards: ``Vault.load_persona`` happens to fail safely (it
pre-checks ``manifest_path.exists()``, and pathlib's own ``.exists()``
swallows ``OSError`` -- including ``NotADirectoryError`` -- and returns a
clean ``False``, so ``load_persona`` raises its own tidy
``FileNotFoundError``). ``Vault.create_returned_session`` does not take
that path -- it calls ``simple_yaml.load_file`` directly, which performs
a raw file read and raises an **uncaught** ``NotADirectoryError``
instead.

This is a PersonaVault Core issue (in ``_resolve_persona_dir`` itself),
not something a tool's own JSON schema can fix at the source, and not
something to patch mid-slice. Rather than modify Core, both adapter
tools reject any persona-name input that could reach this path at all,
before PersonaVault ever sees it. See the Slice 3 report for the
precise, NOT-YET-IMPLEMENTED proposed Core fix (scoping
``_resolve_persona_dir``'s join to reject an absolute
``name_or_folder``) recommended for separate review.
"""

from __future__ import annotations


class UnsafePersonaNameError(ValueError):
    """Raised when a persona-name input is structurally unsafe to pass
    into PersonaVault at all -- never raised for a merely nonexistent,
    well-shaped name (that case is PERSONA_NOT_FOUND, decided by
    PersonaVault's own resolution, not by this guard)."""


def assert_persona_name_is_safe(persona: str) -> None:
    if not persona or not persona.strip():
        raise UnsafePersonaNameError("Persona name must not be empty.")
    if persona.startswith("/") or persona.startswith("\\"):
        raise UnsafePersonaNameError("Persona name must not be an absolute path.")
    if len(persona) > 1 and persona[1] == ":" and persona[0].isalpha():
        # Windows drive-letter absolute path, e.g. "C:\\Users\\...".
        raise UnsafePersonaNameError("Persona name must not be an absolute path.")
    if "/" in persona or "\\" in persona:
        raise UnsafePersonaNameError("Persona name must not contain a path separator.")
    if ".." in persona:
        raise UnsafePersonaNameError("Persona name must not contain '..'.")
