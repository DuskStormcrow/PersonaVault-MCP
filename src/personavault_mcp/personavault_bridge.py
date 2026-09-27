"""Bridges to PersonaVault Core without installing it as a pip package.

Discovered fact (checked directly, not assumed): PersonaVault Core ships
no ``pyproject.toml``, ``setup.py``, or ``setup.cfg`` at its repo root.
``pip install -e <checkout>`` fails outright with "does not appear to be
a Python project" -- there is no build backend for pip to use, editable
or otherwise. Making PersonaVault pip-installable would require adding
packaging metadata to PersonaVault Core, which is a Core change and is
therefore explicitly NOT done here (see the Slice 2 report for why this
does not rise to the "genuinely impossible without a Core change" bar --
a Core-free alternative exists, below).

Instead, this adapter references a PersonaVault checkout by filesystem
path and adds it to ``sys.path`` at call time, the same way PersonaVault's
own CLI already resolves an arbitrary ``--vault-root``. This is the
least-coupled practical option available today:

- no PersonaVault source is vendored or copied into this repo;
- no change to PersonaVault Core is required;
- the exact commit this adapter was written and verified against is
  recorded below.

If PersonaVault Core later adds standard packaging metadata, this module
should be replaced by a normal dependency line in pyproject.toml -- that
is a recommendation for a future, separately reviewed PersonaVault Core
change, not something this adapter performs on its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The PersonaVault commit this adapter's Slice 2 implementation was
# written and verified against. Not enforced automatically in v0.1 --
# available for a caller (or a future slice) to check against.
EXPECTED_PERSONAVAULT_COMMIT = "f9712aceda1912c6e5913bb4b29fc28ed4408933"


class PersonaVaultSourceNotFoundError(RuntimeError):
    """Raised when the configured PersonaVault source path does not look
    like a PersonaVault checkout (no personavault/ package inside it).

    Callers must not surface this exception's message to a host directly
    -- it may contain a filesystem path. Map it to a generic,
    fixed-string error instead.
    """


def ensure_personavault_importable(source_path: Path) -> None:
    """Make ``import personavault`` resolve against the given checkout,
    without installing anything and without modifying PersonaVault Core.

    Idempotent: safe to call more than once.
    """
    source_path = Path(source_path)
    package_marker = source_path / "personavault" / "__init__.py"
    if not package_marker.is_file():
        raise PersonaVaultSourceNotFoundError(
            f"{source_path} does not look like a PersonaVault checkout "
            f"(expected to find {package_marker})."
        )
    resolved = str(source_path.resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


def import_vault_class():
    """Import and return the PersonaVault ``Vault`` class.

    Callers must call ``ensure_personavault_importable`` first, with a
    valid source path, or this will raise ``ModuleNotFoundError`` from
    the ordinary Python import machinery.
    """
    from personavault.storage import Vault  # the one place this adapter
    # imports PersonaVault's own read interface; reachable only once a
    # real source path has been configured and validated above.

    return Vault
