"""Tests for models and configuration parsing."""

from __future__ import annotations

import pytest

from ubiquiti_unifi_blade_mcp.models import (
    is_write_enabled,
    network_spec_from_args,
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


class TestApiKeyConfig:
    def test_session_auth_mode(self, mock_env: None) -> None:
        controllers = parse_controllers()
        assert controllers[0].api_key == ""
        assert controllers[0].auth_mode == "session"

    def test_single_api_key_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UNIFI_CONTROLLERS", raising=False)
        monkeypatch.delenv("UNIFI_USERNAME", raising=False)
        monkeypatch.delenv("UNIFI_PASSWORD", raising=False)
        monkeypatch.setenv("UNIFI_HOST", "10.1.1.1")
        monkeypatch.setenv("UNIFI_API_KEY", "key-abc")
        controllers = parse_controllers()
        assert len(controllers) == 1
        assert controllers[0].api_key == "key-abc"
        assert controllers[0].auth_mode == "apikey"

    def test_multi_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNIFI_CONTROLLERS", "sandybay")
        monkeypatch.setenv("UNIFI_SANDYBAY_HOST", "10.1.1.1")
        monkeypatch.setenv("UNIFI_SANDYBAY_API_KEY", "k")
        controllers = parse_controllers()
        assert len(controllers) == 1
        assert controllers[0].name == "sandybay"
        assert controllers[0].api_key == "k"
        assert controllers[0].auth_mode == "apikey"

    def test_host_only_is_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UNIFI_CONTROLLERS", raising=False)
        monkeypatch.delenv("UNIFI_USERNAME", raising=False)
        monkeypatch.delenv("UNIFI_PASSWORD", raising=False)
        monkeypatch.delenv("UNIFI_API_KEY", raising=False)
        monkeypatch.setenv("UNIFI_HOST", "10.1.1.1")
        with pytest.raises(ValueError, match="UniFi credentials not configured"):
            parse_controllers()


class TestNetworkSpec:
    def test_full_spec(self) -> None:
        spec = network_spec_from_args(
            "Services",
            40,
            subnet="10.1.40.254/24",
            gateway="10.1.40.254",
            dhcp_start="10.1.40.100",
            dhcp_stop="10.1.40.200",
        )
        assert spec["name"] == "Services"
        assert spec["vlanId"] == 40
        assert spec["purpose"] == "corporate"
        assert spec["ipSubnet"] == "10.1.40.254/24"
        assert spec["gatewayIp"] == "10.1.40.254"
        assert spec["dhcpEnabled"] is True
        assert spec["dhcpStart"] == "10.1.40.100"
        assert spec["dhcpStop"] == "10.1.40.200"

    def test_minimal_spec(self) -> None:
        spec = network_spec_from_args("Guest", 30)
        assert spec == {"name": "Guest", "enabled": True, "vlanId": 30, "purpose": "corporate"}

    def test_partial_dhcp_omitted(self) -> None:
        # Only one of start/stop -> no DHCP keys emitted.
        spec = network_spec_from_args("X", 5, dhcp_start="10.0.5.100")
        assert "dhcpEnabled" not in spec
        assert "dhcpStart" not in spec


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
