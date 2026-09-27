"""Slice 5 bind-policy tests: items 1-3. Fast, no real server needed --
these exercise assert_bind_policy_is_safe / build_app's own validation
directly."""

from __future__ import annotations

import pytest

from personavault_mcp.config import AdapterConfig, LOOPBACK_HOSTS, NonLoopbackBindError
from personavault_mcp.registry import reset_registry_for_tests
from personavault_mcp.server import build_app


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


# --- 1: server binds to 127.0.0.1 by default --------------------------------

def test_default_bind_host_is_loopback() -> None:
    assert AdapterConfig().bind_host == "127.0.0.1"


def test_build_app_succeeds_with_default_config(tmp_path) -> None:
    config = AdapterConfig(vault_root=tmp_path / "vault")
    app = build_app(config)
    assert app is not None


# --- 2: default configuration never binds to 0.0.0.0 ------------------------

def test_default_config_never_uses_0_0_0_0() -> None:
    assert AdapterConfig().bind_host != "0.0.0.0"
    assert AdapterConfig.from_env().bind_host != "0.0.0.0"


def test_0_0_0_0_is_not_in_loopback_allowlist() -> None:
    assert "0.0.0.0" not in LOOPBACK_HOSTS


# --- 3: non-loopback bind rejected -------------------------------------------

@pytest.mark.parametrize(
    "non_loopback_host",
    ["0.0.0.0", "192.168.1.5", "10.0.0.1", "example.com", "::"],
)
def test_non_loopback_bind_is_rejected(tmp_path, non_loopback_host) -> None:
    config = AdapterConfig(vault_root=tmp_path / "vault", bind_host=non_loopback_host)
    with pytest.raises(NonLoopbackBindError):
        build_app(config)


@pytest.mark.parametrize("loopback_host", sorted(LOOPBACK_HOSTS))
def test_every_recognized_loopback_host_is_accepted(tmp_path, loopback_host) -> None:
    config = AdapterConfig(vault_root=tmp_path / "vault", bind_host=loopback_host)
    app = build_app(config)
    assert app is not None
