"""Tests for UniFi client wrapper."""

from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from ubiquiti_unifi_blade_mcp.client import UniFiClient, UniFiError, _scrub
from ubiquiti_unifi_blade_mcp.models import network_spec_from_args


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

    def test_scrub_api_key(self) -> None:
        assert "REDACTED" in _scrub("x-api-key: abcdef123456")
        assert "abcdef123456" not in _scrub("x-api-key: abcdef123456")

    def test_scrub_apikey_equals(self) -> None:
        assert "REDACTED" in _scrub("apikey=secretvalue")


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

    def test_apikey_only_controller(self, mock_env_apikey: None) -> None:
        client = UniFiClient()
        assert client.controller_names == ["default"]


class TestNormalizeNetwork:
    def test_camelcase(self) -> None:
        n = UniFiClient._normalize_network(
            {"id": "n1", "name": "Services", "vlanId": 40, "enabled": True, "ipSubnet": "10.1.40.254/24"}
        )
        assert n == {
            "id": "n1",
            "name": "Services",
            "enabled": True,
            "vlan": 40,
            "purpose": "",
            "subnet": "10.1.40.254/24",
            "gateway": "",
        }

    def test_snakecase(self) -> None:
        n = UniFiClient._normalize_network(
            {"_id": "n2", "name": "IoT", "vlan": 20, "ip_subnet": "10.1.20.254/24", "purpose": "corporate"}
        )
        assert n["id"] == "n2"
        assert n["vlan"] == 20
        assert n["subnet"] == "10.1.20.254/24"
        assert n["purpose"] == "corporate"


class TestNetworkClient:
    async def test_get_networks_path_and_parse(self, mock_env_apikey: None, mocker: MockerFixture) -> None:
        client = UniFiClient()
        mocker.patch.object(client, "_resolve_integration_site_id", return_value="SITE-UUID")
        req = mocker.patch.object(
            client,
            "_integration_request",
            return_value={"data": [{"id": "n1", "name": "Services", "vlanId": 40, "enabled": True}]},
        )
        nets = await client.get_networks()
        req.assert_awaited_once_with("get", "sites/SITE-UUID/networks", controller=None)
        assert nets[0]["name"] == "Services"
        assert nets[0]["vlan"] == 40

    async def test_create_network_payload(self, mock_env_apikey: None, mocker: MockerFixture) -> None:
        client = UniFiClient()
        mocker.patch.object(client, "_resolve_integration_site_id", return_value="S")
        req = mocker.patch.object(
            client, "_integration_request", return_value={"id": "new1", "name": "Services", "vlanId": 40}
        )
        spec = network_spec_from_args("Services", 40, subnet="10.1.40.254/24")
        net = await client.create_network(spec)
        req.assert_awaited_once_with("post", "sites/S/networks", controller=None, json_body=spec)
        assert net["id"] == "new1"

    async def test_delete_network(self, mock_env_apikey: None, mocker: MockerFixture) -> None:
        client = UniFiClient()
        mocker.patch.object(client, "_resolve_integration_site_id", return_value="S")
        req = mocker.patch.object(client, "_integration_request", return_value=None)
        assert await client.delete_network("n1") is True
        req.assert_awaited_once_with("delete", "sites/S/networks/n1", controller=None)

    async def test_resolve_site_id_matches_name_and_caches(self, mock_env_apikey: None, mocker: MockerFixture) -> None:
        client = UniFiClient()
        req = mocker.patch.object(
            client,
            "_integration_request",
            return_value={"data": [{"id": "u1", "name": "default"}, {"id": "u2", "name": "other"}]},
        )
        assert await client._resolve_integration_site_id() == "u1"
        assert await client._resolve_integration_site_id() == "u1"  # cached
        req.assert_awaited_once()

    async def test_integration_request_requires_api_key(self, mock_env: None, mocker: MockerFixture) -> None:
        # mock_env has username/password but no API key
        client = UniFiClient()
        with pytest.raises(UniFiError, match="no API key"):
            await client._integration_request("get", "sites")

    async def test_apikey_only_rejects_session_tool(self, mock_env_apikey: None) -> None:
        client = UniFiClient()
        with pytest.raises(UniFiError, match="session auth"):
            await client._get_controller()


class TestGenericIntegrationResources:
    async def test_list_path_and_unwrap(self, mock_env_apikey: None, mocker: MockerFixture) -> None:
        client = UniFiClient()
        mocker.patch.object(client, "_resolve_integration_site_id", return_value="S")
        req = mocker.patch.object(
            client, "_integration_request", return_value={"data": [{"id": "w1", "name": "Guest WiFi"}]}
        )
        items = await client.integration_list("wifi")
        req.assert_awaited_once_with("get", "sites/S/wifi/broadcasts", controller=None)
        assert items[0]["name"] == "Guest WiFi"

    async def test_get_path(self, mock_env_apikey: None, mocker: MockerFixture) -> None:
        client = UniFiClient()
        mocker.patch.object(client, "_resolve_integration_site_id", return_value="S")
        req = mocker.patch.object(client, "_integration_request", return_value={"id": "d1", "domain": "x"})
        item = await client.integration_get("dns_policies", "d1")
        req.assert_awaited_once_with("get", "sites/S/dns/policies/d1", controller=None)
        assert item["domain"] == "x"  # type: ignore[index]

    async def test_create_path_and_body(self, mock_env_apikey: None, mocker: MockerFixture) -> None:
        client = UniFiClient()
        mocker.patch.object(client, "_resolve_integration_site_id", return_value="S")
        req = mocker.patch.object(client, "_integration_request", return_value={"id": "p1"})
        body = {"name": "Block IoT", "action": "BLOCK"}
        await client.integration_create("firewall_policies", body)
        req.assert_awaited_once_with("post", "sites/S/firewall/policies", controller=None, json_body=body)

    async def test_delete_path(self, mock_env_apikey: None, mocker: MockerFixture) -> None:
        client = UniFiClient()
        mocker.patch.object(client, "_resolve_integration_site_id", return_value="S")
        req = mocker.patch.object(client, "_integration_request", return_value=None)
        assert await client.integration_delete("acl_rules", "r1") is True
        req.assert_awaited_once_with("delete", "sites/S/acl-rules/r1", controller=None)

    async def test_read_only_rejects_write(self, mock_env_apikey: None) -> None:
        client = UniFiClient()
        with pytest.raises(UniFiError, match="read-only"):
            await client.integration_create("wan_interfaces", {"x": 1})

    async def test_unknown_resource_rejected(self, mock_env_apikey: None) -> None:
        client = UniFiClient()
        with pytest.raises(UniFiError, match="Unknown Integration-API resource"):
            await client.integration_list("bogus")
