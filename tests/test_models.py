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
    def test_full_gateway_spec(self) -> None:
        # purpose=corporate -> management=GATEWAY with nested ipv4Configuration.
        spec = network_spec_from_args(
            "Services",
            40,
            subnet="10.1.40.254/24",
            gateway="10.1.40.254",
            dhcp_start="10.1.40.100",
            dhcp_stop="10.1.40.200",
        )
        assert spec["management"] == "GATEWAY"
        assert spec["name"] == "Services"
        assert spec["vlanId"] == 40
        # Required non-null GATEWAY scalars.
        assert spec["isolationEnabled"] is False
        assert spec["cellularBackupEnabled"] is False
        assert spec["internetAccessEnabled"] is True
        ipv4 = spec["ipv4Configuration"]
        assert ipv4 == {
            "autoScaleEnabled": False,
            "hostIpAddress": "10.1.40.254",
            "prefixLength": 24,
            "dhcpConfiguration": {
                "mode": "SERVER",
                "ipAddressRange": {"start": "10.1.40.100", "stop": "10.1.40.200"},
                "leaseTimeSeconds": 86400,
                "pingConflictDetectionEnabled": True,
            },
        }
        # Legacy flat keys are gone.
        assert "purpose" not in spec
        assert "ipSubnet" not in spec

    def test_vlan_only_spec_is_unmanaged_no_l3(self) -> None:
        # purpose=vlan-only -> management=UNMANAGED, no ipv4Configuration (the proven probe shape).
        spec = network_spec_from_args("zz-probe", 4090, purpose="vlan-only", enabled=False)
        assert spec == {"management": "UNMANAGED", "name": "zz-probe", "enabled": False, "vlanId": 4090}

    def test_minimal_spec_defaults_to_gateway(self) -> None:
        spec = network_spec_from_args("Guest", 30)
        # Default purpose=corporate -> GATEWAY; no subnet -> no ipv4Configuration emitted,
        # but the required non-null GATEWAY scalars are still present.
        assert spec == {
            "management": "GATEWAY",
            "name": "Guest",
            "enabled": True,
            "vlanId": 30,
            "isolationEnabled": False,
            "cellularBackupEnabled": False,
            "internetAccessEnabled": True,
        }

    def test_gateway_subnet_host_used_when_no_gateway_arg(self) -> None:
        spec = network_spec_from_args("S", 5, subnet="10.0.5.1/24")
        assert spec["ipv4Configuration"] == {
            "autoScaleEnabled": False,
            "hostIpAddress": "10.0.5.1",
            "prefixLength": 24,
        }

    def test_partial_dhcp_omitted(self) -> None:
        # Only one of start/stop -> no dhcpConfiguration emitted.
        spec = network_spec_from_args("X", 5, subnet="10.0.5.1/24", dhcp_start="10.0.5.100")
        assert "dhcpConfiguration" not in spec["ipv4Configuration"]  # type: ignore[operator]


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
