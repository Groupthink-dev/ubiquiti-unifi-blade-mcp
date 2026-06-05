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

    def test_controllers_summary_single(self, mock_env: None) -> None:
        client = UniFiClient()
        assert client.controllers_summary() == [
            {"name": "default", "host": "192.168.1.1", "default": True},
        ]

    def test_controllers_summary_multi_marks_first_default(self, mock_env_multi: None) -> None:
        client = UniFiClient()
        summary = client.controllers_summary()
        assert [c["name"] for c in summary] == ["home", "office"]
        assert summary[0] == {"name": "home", "host": "192.168.1.1", "default": True}
        assert summary[1]["default"] is False


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


class TestDualAuthMode:
    """Prove a controller with both session creds AND an API key serves both tool families.

    The `auth_mode` property is a cosmetic label ("apikey" when api_key is set) — it is
    NOT a routing gate. The actual routing checks each credential field independently:
    - `_get_controller()` checks `config.username and config.password` (session/aiounifi tools)
    - `_integration_request()` checks `config.api_key` (Integration API / network tools)
    Setting both credentials enables both tool families simultaneously on the same controller.
    """

    @pytest.fixture()
    def dual_creds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UNIFI_CONTROLLERS", raising=False)
        monkeypatch.setenv("UNIFI_HOST", "10.0.0.1")
        monkeypatch.setenv("UNIFI_USERNAME", "admin")
        monkeypatch.setenv("UNIFI_PASSWORD", "secret")
        monkeypatch.setenv("UNIFI_API_KEY", "key-xyz")

    def test_parse_stores_both_credentials(self, dual_creds: None) -> None:
        """Both credential fields are populated — no either/or exclusion at parse time."""
        from ubiquiti_unifi_blade_mcp.models import parse_controllers

        controllers = parse_controllers()
        c = controllers[0]
        assert c.username == "admin"
        assert c.password == "secret"
        assert c.api_key == "key-xyz"

    def test_auth_mode_is_cosmetic_not_a_routing_gate(self, dual_creds: None) -> None:
        """auth_mode says 'apikey' when both are set — but session routing is independent."""
        from ubiquiti_unifi_blade_mcp.models import parse_controllers

        controllers = parse_controllers()
        c = controllers[0]
        # auth_mode returns "apikey" when api_key is set — this is the LABEL, not the gate
        assert c.auth_mode == "apikey"
        # The session-auth fields are still populated; _get_controller will NOT raise
        assert c.username and c.password  # session path remains available

    async def test_integration_api_works_with_dual_creds(self, dual_creds: None, mocker: MockerFixture) -> None:
        """API-key path (_integration_request) serves network/VLAN tools even with session creds present."""
        client = UniFiClient()
        mocker.patch.object(client, "_resolve_integration_site_id", return_value="S")
        mocker.patch.object(
            client,
            "_integration_request",
            return_value={"data": [{"id": "n1", "name": "LAN", "enabled": True}]},
        )
        nets = await client.get_networks()
        assert nets[0]["name"] == "LAN"

    async def test_session_auth_works_with_dual_creds(self, dual_creds: None, mocker: MockerFixture) -> None:
        """Session path (_get_controller → aiounifi login) works when api_key is also set.

        Contrast with test_apikey_only_rejects_session_tool (api-key-only raises an
        error about missing username/password). Dual-mode does NOT trigger that error
        because username + password are present.
        """
        client = UniFiClient()
        mock_session = mocker.MagicMock()
        mocker.patch("ubiquiti_unifi_blade_mcp.client.aiohttp.ClientSession", return_value=mock_session)
        mock_ctrl = mocker.MagicMock()
        mock_ctrl.login = mocker.AsyncMock()
        mock_ctrl.devices.update = mocker.AsyncMock()
        mock_ctrl.devices.items.return_value = []
        mocker.patch("ubiquiti_unifi_blade_mcp.client.Controller", return_value=mock_ctrl)

        devices = await client.get_devices()

        # Session auth executed — no "no username/password" error raised
        mock_ctrl.login.assert_awaited_once()
        assert devices == []


class _FakeResponse:
    """Minimal async-context-manager stand-in for aiohttp's response."""

    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeSession:
    """Records every request's headers and replays a scripted sequence of responses."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses
        self.closed = False
        self.calls: list[dict[str, object]] = []

    def request(self, method: str, url: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"method": method, "url": url, "headers": kwargs.get("headers")})
        return self._responses[len(self.calls) - 1]


class TestIntegrationTransportIsolation:
    """A failed Integration-API write must not poison the X-API-KEY read path (regression)."""

    async def test_403_write_does_not_poison_subsequent_read(
        self, mock_env_apikey: None, mocker: MockerFixture
    ) -> None:
        """403 on POST, then GET still carries X-API-KEY and succeeds — the bug.

        Repro from infra-workstation 2026-06-05: a 403 on create poisoned the
        API-key path so every later read returned 401 missing-credentials.
        """
        client = UniFiClient()
        fake = _FakeSession(
            [
                _FakeResponse(403, '{"code":"api.forbidden"}'),  # the failed write
                _FakeResponse(200, '{"data":[{"id":"n1","name":"LAN"}]}'),  # the next read
            ]
        )
        # Inject our fake as the controller's Integration-API session.
        client._integration_sessions["default"] = fake  # type: ignore[assignment]

        # 1) The write is forbidden — surfaced with an Admin-role hint, not a raw auth error.
        from ubiquiti_unifi_blade_mcp.client import AuthError

        with pytest.raises(AuthError, match="forbidden \\(403\\).*Admin role"):
            await client._integration_request("post", "sites/S/networks", json_body={"x": 1})

        # 2) The very next read succeeds AND still carried the X-API-KEY header.
        data = await client._integration_request("get", "sites/S/networks")
        assert data == {"data": [{"id": "n1", "name": "LAN"}]}

        get_headers = fake.calls[1]["headers"]
        assert get_headers is not None
        assert get_headers.get("X-API-KEY") == "test-api-key"  # type: ignore[union-attr]

    async def test_integration_session_is_isolated_from_aiounifi_session(self, mock_env_apikey: None) -> None:
        """The X-API-KEY session is a distinct object with a no-op (Dummy) cookie jar."""
        import aiohttp

        client = UniFiClient()
        try:
            integ = client._ensure_integration_session("default")
            cookie = client._ensure_session("default")
            assert integ is not cookie
            assert isinstance(integ.cookie_jar, aiohttp.DummyCookieJar)
        finally:
            await client.close()

    async def test_401_message_names_the_api_key(self, mock_env_apikey: None) -> None:
        """A genuine 401 is surfaced as a missing/invalid-key message (not lumped with 403)."""
        from ubiquiti_unifi_blade_mcp.client import AuthError

        client = UniFiClient()
        client._integration_sessions["default"] = _FakeSession(  # type: ignore[assignment]
            [_FakeResponse(401, '{"code":"api.authentication.missing-credentials"}')]
        )
        with pytest.raises(AuthError, match="unauthorized \\(401\\).*API key"):
            await client._integration_request("get", "sites/S/networks")
