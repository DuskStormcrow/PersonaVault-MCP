"""Local MCP transport for PersonaVault-MCP.

Streamable HTTP, loopback-only by default, dispatching through the
existing tool registry (personavault_mcp.registry /
personavault_mcp.bootstrap) rather than duplicating tool logic here.
This module owns transport, binding, and error-sanitization only -- it
never talks to PersonaVault directly and never contains tool business
logic.

Library choice (see the Slice 5 report for the full evaluation):
``mcp`` (the official Model Context Protocol Python SDK) pinned to the
1.x line (``mcp>=1.30.0,<2``), specifically because 1.30.0's
``mcp.types.LATEST_PROTOCOL_VERSION`` is exactly ``2025-11-25`` -- the
spec level this project targets, an exact match rather than merely
"newer, presumably compatible" (the 2.x line's LATEST is a later date).
1.30.0 also keeps the classic ``FastMCP`` name and the low-level
``Server.list_tools()`` / ``Server.call_tool()`` decorator API, both
still fully supported (the `mcp` package's own 2.x import error
explicitly frames pinning ``mcp<2`` as an intentional, supported
migration path, not a warning against unmaintained code).

Why the low-level ``Server`` (accessed via ``FastMCP()._mcp_server``),
not FastMCP's own high-level ``add_tool``/``@app.tool()``: those
high-level APIs always *infer* a JSON schema from a Python function's
type hints -- there is no parameter anywhere in ``FastMCP.add_tool`` or
``Tool.from_function`` to supply an explicit schema (checked directly
against the installed library's signatures). Our tools already carry
hand-built, strict schemas (``additionalProperties: false``, enums
sourced from PersonaVault's own constants) that must reach the wire
verbatim -- inferring a new schema from a wrapper function's signature
would risk silently diverging from them. The low-level ``Server``'s
``list_tools()``/``call_tool()`` decorators are the primary public API
of the ``mcp`` package for exactly this case: ``list_tools()`` returns
``types.Tool`` objects we construct ourselves, schema included verbatim;
``call_tool(validate_input=True)`` uses real ``jsonschema.validate``
against that exact schema before our own handler ever runs (verified by
reading the installed library's source), then dispatches to whatever we
return. ``FastMCP`` itself is used only for its tested Streamable HTTP
serving machinery (``run(transport="streamable-http")``); a fresh
instance advertises zero tools/resources/prompts by default (verified
directly), so nothing from the framework is exposed outside our own
registry.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp import types
from mcp.server.fastmcp import FastMCP

from . import bootstrap
from .config import AdapterConfig, NonLoopbackBindError, assert_bind_policy_is_safe
from .registry import TOOL_REGISTRY
from .server_metadata import ADAPTER_NAME, ADAPTER_VERSION
from .tools.get_boot_context import BootContextError
from .tools.propose_session_note import ProposeSessionNoteError

logger = logging.getLogger("personavault_mcp.server")

# Human-readable descriptions surfaced to a connecting client via
# list_tools(). Not part of the input/output contract -- purely
# descriptive text, safe to keep here rather than in the tool modules
# themselves, which own schemas and behavior, not transport-facing copy.
_TOOL_DESCRIPTIONS = {
    "get_boot_context": (
        "Read-only, bounded PersonaVault boot context (identity, memory "
        "rules, boot prompt, up to the latest approved continuity "
        "events) for one active resident."
    ),
    "propose_session_note": (
        "Propose something learned during this interaction as a "
        "candidate for PersonaVault's Session Return review. Never "
        "approves, commits, or writes canonical continuity -- every "
        "proposal is recorded pending human review."
    ),
}


def _error_result(code: str, message: str) -> types.CallToolResult:
    """Every adapter-error path (typed or unexpected) goes through this
    single function, so every error the client sees has the same
    ``CODE: message`` shape and never carries a raw exception string,
    traceback, or filesystem path -- both tool modules already raise
    only fixed, generic messages (established in Slices 2-3), so
    ``message`` here is always safe to include verbatim."""
    return types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text=f"{code}: {message}")],
    )


def build_app(config: AdapterConfig) -> FastMCP:
    """Build (but do not run) the MCP application for the given config.

    Raises ``NonLoopbackBindError`` before anything else happens if
    ``config.bind_host`` is not a recognized loopback address --
    configuration is validated before any registration or binding.
    """
    assert_bind_policy_is_safe(config)

    # Idempotent: registering twice (e.g. if build_app is called more
    # than once in a test) leaves the registry at exactly the same two
    # tools -- registry.register_tool's own allowlist re-asserts this
    # every time regardless.
    bootstrap.register_default_tools()

    app = FastMCP(
        ADAPTER_NAME,
        instructions=f"PersonaVault MCP Adapter {ADAPTER_VERSION}",
        host=config.bind_host,
        port=config.bind_port,
    )

    # See module docstring for why this is the underlying low-level
    # Server, not FastMCP's own add_tool/@app.tool() sugar.
    server = app._mcp_server

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=spec.name,
                description=_TOOL_DESCRIPTIONS.get(spec.name, ""),
                inputSchema=dict(spec.input_schema),
            )
            for spec in TOOL_REGISTRY.values()
        ]

    @server.call_tool(validate_input=True)
    async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any] | types.CallToolResult:
        spec = TOOL_REGISTRY.get(name)
        if spec is None or spec.handler is None:
            logger.info("tool invocation rejected: unknown tool %r", name)
            return _error_result("UNSUPPORTED_OPERATION", f"Unknown tool: {name}")

        try:
            result = spec.handler(arguments, config=config)
        except (BootContextError, ProposeSessionNoteError) as exc:
            logger.info("tool invocation failed: %s -> %s", name, exc.code)
            return _error_result(exc.code, str(exc))
        except Exception:
            # Deliberately does not include str(exc): an exception this
            # tool didn't itself raise and type is, by definition,
            # unexpected, and might carry a path or other internal
            # detail neither tool module was designed to sanitize.
            logger.exception("tool invocation raised an unexpected error: %s", name)
            return _error_result("INTERNAL_ADAPTER_ERROR", "An unexpected error occurred.")

        logger.info("tool invocation succeeded: %s", name)
        return result

    return app


def main() -> int:
    """Console entry point. Validates configuration, binds, serves, and
    returns a process exit code -- never raises out of this function."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    config = AdapterConfig.from_env()

    try:
        app = build_app(config)
    except NonLoopbackBindError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    logger.info(
        "%s starting on %s:%d (streamable-http, /mcp)",
        ADAPTER_NAME,
        config.bind_host,
        config.bind_port,
    )
    try:
        app.run(transport="streamable-http")
    except SystemExit as exc:
        # uvicorn's own startup path (used internally by
        # app.run(transport="streamable-http")) does not let a bind
        # failure (e.g. "address already in use") propagate as a plain
        # OSError -- verified directly: it catches OSError itself and
        # calls sys.exit(STARTUP_FAILURE) (value 3 in the installed
        # uvicorn version), already logging a clear error to stderr on
        # its own. Only that specific, known startup-failure code is
        # translated into our own clean message; any other SystemExit
        # (e.g. a normal shutdown) is left to mean exactly what it says
        # and is not misreported as a startup failure.
        from uvicorn.server import STARTUP_FAILURE

        if exc.code == STARTUP_FAILURE:
            print(
                f"Startup failed: could not bind {config.bind_host}:{config.bind_port} "
                "(the port is likely already in use).",
                file=sys.stderr,
            )
            return STARTUP_FAILURE
        raise

    logger.info("%s stopped", ADAPTER_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
