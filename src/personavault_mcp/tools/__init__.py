"""Functional MCP tool implementations.

Each tool module owns: its input schema, its output allowlist, its error
mapping, and a pure ``handle(raw_input, *, config)`` entry point. Nothing
outside this package's own tool modules calls into PersonaVault directly.
"""
