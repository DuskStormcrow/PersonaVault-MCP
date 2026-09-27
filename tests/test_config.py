"""Config skeleton tests: defaults must stay localhost-first, and
reading config must never touch PersonaVault or the network."""

from __future__ import annotations

from personavault_mcp.config import AdapterConfig


def test_default_config_is_loopback_only() -> None:
    config = AdapterConfig()
    assert config.bind_host == "127.0.0.1"
    assert config.vault_root is None


def test_from_env_defaults_to_loopback_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("PERSONAVAULT_MCP_BIND_HOST", raising=False)
    monkeypatch.delenv("PERSONAVAULT_MCP_VAULT_ROOT", raising=False)
    config = AdapterConfig.from_env()
    assert config.bind_host == "127.0.0.1"
    assert config.vault_root is None


def test_auth_token_field_holds_env_var_name_not_a_secret_value() -> None:
    config = AdapterConfig()
    # This field must be the *name* of an environment variable to read a
    # token from later, never a token value itself, and never a default
    # that looks like usable credential material.
    assert config.auth_token_env_var == "PERSONAVAULT_MCP_AUTH_TOKEN"
    assert config.auth_token_env_var.isupper()
