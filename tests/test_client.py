"""Tests for UniFi client wrapper."""

from __future__ import annotations

import pytest

from ubiquiti_unifi_blade_mcp.client import UniFiClient, UniFiError, _scrub


class TestCredentialScrubbing:
    def test_scrub_password(self) -> None:
        assert "REDACTED" in _scrub("password=mysecret123")

    def test_scrub_cookie(self) -> None:
        assert "REDACTED" in _scrub("cookie=abc123def456")

    def test_scrub_bearer(self) -> None:
        assert "REDACTED" in _scrub("Bearer sk-abc123")

    def test_scrub_csrf(self) -> None:
        assert "REDACTED" in _scrub("x-csrf-token=abc123")

    def test_scrub_unifises(self) -> None:
        assert "REDACTED" in _scrub("unifises=session123cookie")

    def test_scrub_preserves_safe_text(self) -> None:
        safe = "Connection timeout after 30s"
        assert _scrub(safe) == safe


class TestUniFiClientInit:
    def test_single_controller(self, mock_env: None) -> None:
        client = UniFiClient()
        assert client.controller_names == ["default"]

    def test_multi_controller(self, mock_env_multi: None) -> None:
        client = UniFiClient()
        assert client.controller_names == ["home", "office"]

    def test_unknown_controller_raises(self, mock_env: None) -> None:
        client = UniFiClient()
        with pytest.raises(UniFiError, match="Unknown controller"):
            client._get_config("nonexistent")
