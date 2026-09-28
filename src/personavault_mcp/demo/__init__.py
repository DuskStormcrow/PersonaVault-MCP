"""Slice 6: a completely synthetic PersonaVault resident and an isolated,
disposable demo vault, for smoke tests, screenshots, recordings, and
hackathon/external review -- never a real resident, never the real
PersonaVault Library.

See ``fixture.py`` for the resident's content, ``safety.py`` for the
guard rails against ever touching a real vault, and
``build_demo_vault.py`` for the reproducible builder
(``python -m personavault_mcp.demo.build_demo_vault``).
"""

from __future__ import annotations
