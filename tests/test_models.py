"""Tests for models and configuration parsing."""

from __future__ import annotations

import pytest

from ubiquiti_unifi_blade_mcp.models import (
    is_write_enabled,
    parse_controllers,
    require_write,
)


class TestParseControllers:
    def test_single_controller(self, mock_env: None) -> None:
        controllers = parse_controllers()
        assert len(controllers) == 1
        assert controllers[0].name == "default"
        assert controllers[0].host == "192.168.1.1"
        assert controllers[0].username == "admin"
        assert controllers[0].password == "test-password"
        assert controllers[0].port == 443
        assert controllers[0].site == "default"

    def test_multi_controller(self, mock_env_multi: None) -> None:
        controllers = parse_controllers()
        assert len(controllers) == 2
        assert controllers[0].name == "home"
        assert controllers[0].host == "192.168.1.1"
        assert controllers[1].name == "office"
        assert controllers[1].host == "10.0.0.1"

    def test_missing_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UNIFI_HOST", raising=False)
        monkeypatch.delenv("UNIFI_USERNAME", raising=False)
        monkeypatch.delenv("UNIFI_PASSWORD", raising=False)
        monkeypatch.delenv("UNIFI_CONTROLLERS", raising=False)
        with pytest.raises(ValueError, match="UniFi credentials not configured"):
            parse_controllers()

    def test_custom_port_and_site(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNIFI_HOST", "10.0.0.1")
        monkeypatch.setenv("UNIFI_USERNAME", "admin")
        monkeypatch.setenv("UNIFI_PASSWORD", "pass")
        monkeypatch.setenv("UNIFI_PORT", "8443")
        monkeypatch.setenv("UNIFI_SITE", "mysite")
        controllers = parse_controllers()
        assert controllers[0].port == 8443
        assert controllers[0].site == "mysite"

    def test_ssl_verification(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNIFI_HOST", "10.0.0.1")
        monkeypatch.setenv("UNIFI_USERNAME", "admin")
        monkeypatch.setenv("UNIFI_PASSWORD", "pass")
        monkeypatch.setenv("UNIFI_VERIFY_SSL", "true")
        controllers = parse_controllers()
        assert controllers[0].verify_ssl is True

    def test_ssl_default_false(self, mock_env: None) -> None:
        controllers = parse_controllers()
        assert controllers[0].verify_ssl is False


class TestWriteGate:
    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UNIFI_WRITE_ENABLED", raising=False)
        assert not is_write_enabled()
        assert require_write() is not None
        assert "disabled" in require_write().lower()  # type: ignore[union-attr]

    def test_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNIFI_WRITE_ENABLED", "true")
        assert is_write_enabled()
        assert require_write() is None

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNIFI_WRITE_ENABLED", "TRUE")
        assert is_write_enabled()
