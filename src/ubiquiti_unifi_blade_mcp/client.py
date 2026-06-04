"""UniFi controller client wrapper.

Wraps ``aiounifi`` with credential scrubbing, multi-controller support,
and session management. All methods are async — aiounifi is natively async.
"""

from __future__ import annotations

import json
import logging
import re
import ssl
from typing import Any, Literal

import aiohttp
from aiounifi.controller import Controller
from aiounifi.models.api import ApiRequest
from aiounifi.models.configuration import Configuration

from ubiquiti_unifi_blade_mcp.models import ControllerConfig, parse_controllers

logger = logging.getLogger(__name__)

# Base path for the official UniFi Network Integration API (X-API-KEY auth).
_INTEGRATION_BASE = "proxy/network/integration/v1"

# Patterns to scrub from error messages
_CREDENTIAL_PATTERNS = [
    re.compile(r"password[=:]\S+", re.IGNORECASE),
    re.compile(r"cookie[=:]\S+", re.IGNORECASE),
    re.compile(r"x-csrf-token[=:]\S+", re.IGNORECASE),
    re.compile(r"x-api-key[=:]\s*\S+", re.IGNORECASE),
    re.compile(r"api[_-]?key[=:]\s*\S+", re.IGNORECASE),
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"unifises=\S+", re.IGNORECASE),
    re.compile(r"TOKEN=\S+", re.IGNORECASE),
]


class UniFiError(Exception):
    """Base error for UniFi client operations."""


class AuthError(UniFiError):
    """Authentication failed."""


class NotFoundError(UniFiError):
    """Requested resource not found."""


class ConnectionError(UniFiError):
    """Network or controller connection error."""


def _scrub(message: str) -> str:
    """Remove credentials from error messages."""
    for pattern in _CREDENTIAL_PATTERNS:
        message = pattern.sub("[REDACTED]", message)
    return message


class UniFiClient:
    """Multi-controller UniFi API client.

    Wraps aiounifi with:
    - Lazy connection (on first API call per controller)
    - Credential scrubbing on all errors
    - Multi-controller routing (controller param on all methods)
    - Session lifecycle management
    """

    def __init__(self) -> None:
        self._configs = parse_controllers()
        self._controllers: dict[str, Controller] = {}
        self._sessions: dict[str, aiohttp.ClientSession] = {}
        self._connected: set[str] = set()
        # Cache of Integration-API site UUIDs (distinct from the short site name)
        self._site_ids: dict[str, str] = {}

    @property
    def controller_names(self) -> list[str]:
        """Return configured controller names."""
        return [c.name for c in self._configs]

    def _get_config(self, controller: str | None = None) -> ControllerConfig:
        """Get configuration for the given controller."""
        name = controller or self._configs[0].name
        config = next((c for c in self._configs if c.name == name), None)
        if config is None:
            raise UniFiError(f"Unknown controller: {name}. Available: {', '.join(self.controller_names)}")
        return config

    @staticmethod
    def _ssl_param(config: ControllerConfig) -> ssl.SSLContext | Literal[False]:
        """Return an SSL context (verify) or ``False`` (skip — common on UDM)."""
        if config.verify_ssl:
            return ssl.create_default_context()
        return False

    def _ensure_session(self, name: str) -> aiohttp.ClientSession:
        """Get or create the per-controller aiohttp session (shared by both auth modes)."""
        if name not in self._sessions or self._sessions[name].closed:
            self._sessions[name] = aiohttp.ClientSession()
        return self._sessions[name]

    async def _get_controller(self, controller: str | None = None) -> Controller:
        """Get or create an aiounifi Controller for the given controller."""
        name = controller or self._configs[0].name
        if name in self._controllers and name in self._connected:
            return self._controllers[name]

        config = self._get_config(name)

        # Session (cookie/CSRF) auth requires username + password. An api-key-only
        # controller can still serve the network/VLAN tools (Integration API),
        # but not the aiounifi-backed monitoring tools — fail with a clear hint.
        if not (config.username and config.password):
            raise UniFiError(
                f"Controller '{name}' has no username/password — this tool requires "
                "session auth. Only the network/VLAN tools work in API-key-only mode."
            )

        # Create SSL context
        ssl_context = self._ssl_param(config)

        # Create aiohttp session
        session = self._ensure_session(name)

        # Create aiounifi configuration
        unifi_config = Configuration(
            session=session,
            host=config.host,
            username=config.username,
            password=config.password,
            port=config.port,
            site=config.site,
            ssl_context=ssl_context,
        )

        ctrl = Controller(unifi_config)

        try:
            await ctrl.login()
            self._controllers[name] = ctrl
            self._connected.add(name)
            logger.info("Connected to UniFi controller '%s' at %s", name, config.host)
        except Exception as e:
            raise AuthError(_scrub(f"Login failed for controller '{name}': {e}")) from e

        return ctrl

    async def _call(self, controller: str | None = None) -> Controller:
        """Get a connected controller with error handling."""
        try:
            return await self._get_controller(controller)
        except AuthError:
            raise
        except Exception as e:
            raise UniFiError(_scrub(f"Controller error: {e}")) from e

    async def close(self) -> None:
        """Close all sessions."""
        for session in self._sessions.values():
            if not session.closed:
                await session.close()
        self._sessions.clear()
        self._controllers.clear()
        self._connected.clear()

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    async def info(self, controller: str | None = None) -> dict[str, Any]:
        """Health check: controller version, sites, device/client counts."""
        from ubiquiti_unifi_blade_mcp.models import is_write_enabled

        results: list[dict[str, Any]] = []
        controllers_to_check = [controller] if controller else [c.name for c in self._configs]

        for ctrl_name in controllers_to_check:
            try:
                ctrl = await self._call(ctrl_name)
                config = self._get_config(ctrl_name)

                # Fetch system info
                await ctrl.system_information.update()
                sys_info = {}
                for item in ctrl.system_information.values():
                    sys_info = {
                        "version": getattr(item, "version", "?"),
                        "hostname": getattr(item, "hostname", "?"),
                    }
                    break

                # Fetch counts
                await ctrl.devices.update()
                await ctrl.clients.update()
                await ctrl.sites.update()

                results.append(
                    {
                        "controller": ctrl_name,
                        "host": config.host,
                        "status": "connected",
                        "version": sys_info.get("version", "?"),
                        "hostname": sys_info.get("hostname", "?"),
                        "site": config.site,
                        "sites": sum(1 for _ in ctrl.sites.values()),
                        "devices": sum(1 for _ in ctrl.devices.values()),
                        "clients": sum(1 for _ in ctrl.clients.values()),
                    }
                )
            except UniFiError as e:
                results.append({"controller": ctrl_name, "status": "error", "error": str(e)})

        return {
            "controllers": results,
            "total_devices": sum(r.get("devices", 0) for r in results),
            "total_clients": sum(r.get("clients", 0) for r in results),
            "write_enabled": is_write_enabled(),
        }

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    async def get_devices(self, controller: str | None = None) -> list[dict[str, Any]]:
        """Get all network devices."""
        ctrl = await self._call(controller)
        await ctrl.devices.update()
        devices = []
        for mac, device in ctrl.devices.items():
            devices.append(
                {
                    "mac": mac,
                    "name": getattr(device, "name", "") or mac,
                    "model": getattr(device, "model", "?"),
                    "type": getattr(device, "type", "?"),
                    "ip": getattr(device, "ip", ""),
                    "version": getattr(device, "version", ""),
                    "state": getattr(device, "state", 0),
                    "adopted": getattr(device, "adopted", False),
                    "uptime": getattr(device, "uptime", 0),
                    "clients": getattr(device, "num_sta", 0),
                    "upgradeable": getattr(device, "upgradable", False),
                }
            )
        return devices

    async def get_device(self, mac: str, controller: str | None = None) -> dict[str, Any] | None:
        """Get a single device by MAC address."""
        ctrl = await self._call(controller)
        await ctrl.devices.update()
        device = ctrl.devices.get(mac.lower())
        if device is None:
            return None
        port_table = getattr(device, "port_table", []) or []
        ports = []
        for p in port_table:
            ports.append(
                {
                    "port_idx": getattr(p, "port_idx", 0),
                    "name": getattr(p, "name", ""),
                    "up": getattr(p, "up", False),
                    "speed": getattr(p, "speed", 0),
                    "poe_enable": getattr(p, "poe_enable", False),
                    "poe_power": getattr(p, "poe_power", ""),
                }
            )
        return {
            "mac": mac,
            "name": getattr(device, "name", "") or mac,
            "model": getattr(device, "model", "?"),
            "model_name": getattr(device, "model_name", ""),
            "type": getattr(device, "type", "?"),
            "ip": getattr(device, "ip", ""),
            "version": getattr(device, "version", ""),
            "state": getattr(device, "state", 0),
            "adopted": getattr(device, "adopted", False),
            "uptime": getattr(device, "uptime", 0),
            "clients": getattr(device, "num_sta", 0),
            "upgradeable": getattr(device, "upgradable", False),
            "last_seen": getattr(device, "last_seen", 0),
            "ports": ports,
        }

    async def restart_device(self, mac: str, controller: str | None = None) -> bool:
        """Restart a network device."""
        ctrl = await self._call(controller)
        await ctrl.devices.update()
        device = ctrl.devices.get(mac.lower())
        if device is None:
            raise NotFoundError(f"Device {mac} not found")
        # aiounifi device restart via raw API call
        site = ctrl.connectivity.config.site
        await ctrl.request(
            ApiRequest("post", f"/api/s/{site}/cmd/devmgr", {"cmd": "restart", "mac": mac.lower()}),
        )
        return True

    # ------------------------------------------------------------------
    # Clients
    # ------------------------------------------------------------------

    async def get_clients(self, controller: str | None = None) -> list[dict[str, Any]]:
        """Get connected clients."""
        ctrl = await self._call(controller)
        await ctrl.clients.update()
        clients = []
        for mac, client in ctrl.clients.items():
            clients.append(
                {
                    "mac": mac,
                    "name": getattr(client, "name", "") or getattr(client, "hostname", "") or mac,
                    "ip": getattr(client, "ip", ""),
                    "network": getattr(client, "network", ""),
                    "essid": getattr(client, "essid", ""),
                    "is_wired": getattr(client, "is_wired", False),
                    "signal": getattr(client, "rssi", 0) if not getattr(client, "is_wired", False) else None,
                    "experience": getattr(client, "satisfaction", 0),
                    "blocked": getattr(client, "blocked", False),
                    "uptime": getattr(client, "uptime", 0),
                }
            )
        return clients

    async def get_client(self, mac: str, controller: str | None = None) -> dict[str, Any] | None:
        """Get a single client by MAC address."""
        ctrl = await self._call(controller)
        await ctrl.clients.update()
        client = ctrl.clients.get(mac.lower())
        if client is None:
            return None
        return {
            "mac": mac,
            "name": getattr(client, "name", "") or getattr(client, "hostname", "") or mac,
            "hostname": getattr(client, "hostname", ""),
            "ip": getattr(client, "ip", ""),
            "network": getattr(client, "network", ""),
            "essid": getattr(client, "essid", ""),
            "is_wired": getattr(client, "is_wired", False),
            "signal": getattr(client, "rssi", 0) if not getattr(client, "is_wired", False) else None,
            "experience": getattr(client, "satisfaction", 0),
            "blocked": getattr(client, "blocked", False),
            "uptime": getattr(client, "uptime", 0),
            "tx_bytes": getattr(client, "tx_bytes", 0),
            "rx_bytes": getattr(client, "rx_bytes", 0),
            "last_seen": getattr(client, "last_seen", 0),
            "oui": getattr(client, "oui", ""),
            "ap_mac": getattr(client, "ap_mac", ""),
        }

    async def block_client(self, mac: str, controller: str | None = None) -> bool:
        """Block a client."""
        ctrl = await self._call(controller)
        await ctrl.clients.block(mac.lower())
        return True

    async def unblock_client(self, mac: str, controller: str | None = None) -> bool:
        """Unblock a client."""
        ctrl = await self._call(controller)
        await ctrl.clients.unblock(mac.lower())
        return True

    async def reconnect_client(self, mac: str, controller: str | None = None) -> bool:
        """Force a client to reconnect."""
        ctrl = await self._call(controller)
        await ctrl.clients.reconnect(mac.lower())
        return True

    async def forget_client(self, mac: str, controller: str | None = None) -> bool:
        """Remove (forget) a client from the controller."""
        ctrl = await self._call(controller)
        await ctrl.clients.remove_clients([mac.lower()])
        return True

    # ------------------------------------------------------------------
    # WLANs
    # ------------------------------------------------------------------

    async def get_wlans(self, controller: str | None = None) -> list[dict[str, Any]]:
        """Get all WLANs (SSIDs)."""
        ctrl = await self._call(controller)
        await ctrl.wlans.update()
        wlans = []
        for wlan_id, wlan in ctrl.wlans.items():
            wlans.append(
                {
                    "id": wlan_id,
                    "name": getattr(wlan, "name", "?"),
                    "enabled": getattr(wlan, "enabled", False),
                    "security": getattr(wlan, "security", ""),
                    "is_guest": getattr(wlan, "is_guest", False),
                }
            )
        return wlans

    async def enable_wlan(self, wlan_id: str, controller: str | None = None) -> bool:
        """Enable a WLAN."""
        ctrl = await self._call(controller)
        await ctrl.wlans.update()
        wlan = ctrl.wlans.get(wlan_id)
        if wlan is None:
            raise NotFoundError(f"WLAN {wlan_id} not found")
        await ctrl.wlans.enable(wlan)
        return True

    async def disable_wlan(self, wlan_id: str, controller: str | None = None) -> bool:
        """Disable a WLAN."""
        ctrl = await self._call(controller)
        await ctrl.wlans.update()
        wlan = ctrl.wlans.get(wlan_id)
        if wlan is None:
            raise NotFoundError(f"WLAN {wlan_id} not found")
        await ctrl.wlans.disable(wlan)
        return True

    # ------------------------------------------------------------------
    # Firewall & Security
    # ------------------------------------------------------------------

    async def get_firewall_policies(self, controller: str | None = None) -> list[dict[str, Any]]:
        """Get firewall policies."""
        ctrl = await self._call(controller)
        await ctrl.firewall_policies.update()
        policies = []
        for policy_id, policy in ctrl.firewall_policies.items():
            policies.append(
                {
                    "id": policy_id,
                    "name": getattr(policy, "name", "?"),
                    "enabled": getattr(policy, "enabled", False),
                    "action": getattr(policy, "action", ""),
                    "source": getattr(policy, "source", {}),
                    "destination": getattr(policy, "destination", {}),
                }
            )
        return policies

    async def get_traffic_routes(self, controller: str | None = None) -> list[dict[str, Any]]:
        """Get traffic routes."""
        ctrl = await self._call(controller)
        await ctrl.traffic_routes.update()
        routes = []
        for route_id, route in ctrl.traffic_routes.items():
            routes.append(
                {
                    "id": route_id,
                    "description": getattr(route, "description", "?"),
                    "enabled": getattr(route, "enabled", False),
                    "matching_target": getattr(route, "matching_target", ""),
                    "target_devices": getattr(route, "target_devices", []),
                }
            )
        return routes

    async def enable_traffic_route(self, route_id: str, controller: str | None = None) -> bool:
        """Enable a traffic route."""
        ctrl = await self._call(controller)
        await ctrl.traffic_routes.update()
        route = ctrl.traffic_routes.get(route_id)
        if route is None:
            raise NotFoundError(f"Traffic route {route_id} not found")
        await ctrl.traffic_routes.enable(route)
        return True

    async def disable_traffic_route(self, route_id: str, controller: str | None = None) -> bool:
        """Disable a traffic route."""
        ctrl = await self._call(controller)
        await ctrl.traffic_routes.update()
        route = ctrl.traffic_routes.get(route_id)
        if route is None:
            raise NotFoundError(f"Traffic route {route_id} not found")
        await ctrl.traffic_routes.disable(route)
        return True

    async def get_traffic_rules(self, controller: str | None = None) -> list[dict[str, Any]]:
        """Get traffic rules."""
        ctrl = await self._call(controller)
        await ctrl.traffic_rules.update()
        rules = []
        for rule_id, rule in ctrl.traffic_rules.items():
            rules.append(
                {
                    "id": rule_id,
                    "description": getattr(rule, "description", "?"),
                    "enabled": getattr(rule, "enabled", False),
                    "action": getattr(rule, "action", ""),
                    "matching_target": getattr(rule, "matching_target", ""),
                    "target_devices": getattr(rule, "target_devices", []),
                }
            )
        return rules

    async def get_port_forwards(self, controller: str | None = None) -> list[dict[str, Any]]:
        """Get port forwarding rules."""
        ctrl = await self._call(controller)
        await ctrl.port_forwarding.update()
        forwards = []
        for fwd_id, fwd in ctrl.port_forwarding.items():
            forwards.append(
                {
                    "id": fwd_id,
                    "name": getattr(fwd, "name", "?"),
                    "enabled": getattr(fwd, "enabled", False),
                    "dst_port": getattr(fwd, "dst_port", ""),
                    "fwd_port": getattr(fwd, "fwd_port", ""),
                    "fwd": getattr(fwd, "fwd", ""),
                    "proto": getattr(fwd, "proto", ""),
                }
            )
        return forwards

    # ------------------------------------------------------------------
    # DPI
    # ------------------------------------------------------------------

    async def get_dpi_restrictions(self, controller: str | None = None) -> dict[str, Any]:
        """Get DPI restriction groups and apps."""
        ctrl = await self._call(controller)
        await ctrl.dpi_groups.update()
        await ctrl.dpi_apps.update()

        groups = []
        for gid, group in ctrl.dpi_groups.items():
            groups.append(
                {
                    "id": gid,
                    "name": getattr(group, "name", "?"),
                    "enabled": getattr(group, "enabled", False),
                }
            )

        apps = []
        for aid, app in ctrl.dpi_apps.items():
            apps.append(
                {
                    "id": aid,
                    "name": getattr(app, "name", "?"),
                    "enabled": getattr(app, "enabled", False),
                    "group_id": getattr(app, "group_id", ""),
                }
            )

        return {"groups": groups, "apps": apps}

    # ------------------------------------------------------------------
    # Sites
    # ------------------------------------------------------------------

    async def get_sites(self, controller: str | None = None) -> list[dict[str, Any]]:
        """Get sites on the controller."""
        ctrl = await self._call(controller)
        await ctrl.sites.update()
        sites = []
        for site_id, site in ctrl.sites.items():
            sites.append(
                {
                    "id": site_id,
                    "name": getattr(site, "name", "?"),
                    "description": getattr(site, "desc", ""),
                }
            )
        return sites

    # ------------------------------------------------------------------
    # Integration API (X-API-KEY) — networks / VLANs
    # ------------------------------------------------------------------

    async def _integration_request(
        self,
        method: str,
        path: str,
        *,
        controller: str | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Make a request against the official UniFi Network Integration API.

        Stateless: authenticates with ``X-API-KEY`` (no login/CSRF). Used by the
        network/VLAN tools. Requires ``api_key`` on the target controller.
        """
        config = self._get_config(controller)
        if not config.api_key:
            raise UniFiError(
                f"Controller '{config.name}' has no API key. Set UNIFI_API_KEY "
                f"(or UNIFI_{config.name.upper()}_API_KEY) to use network/VLAN tools."
            )

        session = self._ensure_session(config.name)
        url = f"https://{config.host}:{config.port}/{_INTEGRATION_BASE}/{path.lstrip('/')}"
        headers = {"X-API-KEY": config.api_key, "Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        try:
            async with session.request(
                method.upper(),
                url,
                headers=headers,
                json=json_body,
                ssl=self._ssl_param(config),
            ) as resp:
                text = await resp.text()
                if resp.status in (401, 403):
                    raise AuthError(_scrub(f"Integration API auth failed ({resp.status}): {text}"))
                if resp.status == 404:
                    raise NotFoundError(_scrub(f"Integration API resource not found ({resp.status}): {text}"))
                if resp.status >= 400:
                    raise UniFiError(_scrub(f"Integration API error ({resp.status}): {text}"))
                if not text:
                    return None
                try:
                    return json.loads(text)
                except json.JSONDecodeError as e:
                    raise UniFiError(_scrub(f"Integration API returned non-JSON response: {e}")) from e
        except aiohttp.ClientError as e:
            raise ConnectionError(_scrub(f"Integration API request failed: {e}")) from e

    async def _resolve_integration_site_id(self, controller: str | None = None) -> str:
        """Resolve the Integration-API site UUID for the configured short site name.

        The Integration API keys sites by UUID, not the legacy ``default`` slug.
        Matches on ``name``; falls back to the sole site, else the first. Cached.
        """
        config = self._get_config(controller)
        cached = self._site_ids.get(config.name)
        if cached:
            return cached

        data = await self._integration_request("get", "sites", controller=controller)
        items = data.get("data", []) if isinstance(data, dict) else (data or [])
        if not items:
            raise NotFoundError(f"No sites returned by the Integration API for controller '{config.name}'")

        chosen = next(
            (s for s in items if str(s.get("name", "")).lower() == config.site.lower()),
            items[0],
        )
        site_id = str(chosen.get("id", ""))
        if not site_id:
            raise NotFoundError(f"Could not resolve a site id for controller '{config.name}'")
        self._site_ids[config.name] = site_id
        return site_id

    @staticmethod
    def _normalize_network(n: dict[str, Any]) -> dict[str, Any]:
        """Normalize a network record across camelCase (Integration API) / snake_case (legacy)."""
        return {
            "id": n.get("id") or n.get("_id", ""),
            "name": n.get("name", "?"),
            "enabled": n.get("enabled", n.get("vlan_enabled", True)),
            "vlan": n.get("vlanId", n.get("vlan")),
            "purpose": n.get("purpose") or n.get("management") or "",
            "subnet": n.get("ipSubnet") or n.get("ip_subnet") or n.get("subnet") or "",
            "gateway": n.get("gatewayIp") or n.get("gateway") or "",
        }

    async def get_networks(self, controller: str | None = None) -> list[dict[str, Any]]:
        """List configured networks / VLANs (Integration API)."""
        site_id = await self._resolve_integration_site_id(controller)
        data = await self._integration_request("get", f"sites/{site_id}/networks", controller=controller)
        items = data.get("data", []) if isinstance(data, dict) else (data or [])
        return [self._normalize_network(n) for n in items]

    async def get_network(self, network_id: str, controller: str | None = None) -> dict[str, Any] | None:
        """Get a single network / VLAN by id (Integration API)."""
        site_id = await self._resolve_integration_site_id(controller)
        data = await self._integration_request("get", f"sites/{site_id}/networks/{network_id}", controller=controller)
        if not data:
            return None
        return self._normalize_network(data)

    async def create_network(self, spec: dict[str, Any], controller: str | None = None) -> dict[str, Any]:
        """Create a network / VLAN (Integration API). ``spec`` is the raw API body."""
        site_id = await self._resolve_integration_site_id(controller)
        data = await self._integration_request(
            "post", f"sites/{site_id}/networks", controller=controller, json_body=spec
        )
        return self._normalize_network(data) if isinstance(data, dict) else {}

    async def update_network(
        self, network_id: str, patch: dict[str, Any], controller: str | None = None
    ) -> dict[str, Any]:
        """Update a network / VLAN (Integration API). Sends only the supplied fields.

        NOTE (Phase 0): confirm whether the v10.4 ``PUT`` requires the full object
        rather than a partial patch; if so, fetch-merge-PUT here.
        """
        site_id = await self._resolve_integration_site_id(controller)
        data = await self._integration_request(
            "put", f"sites/{site_id}/networks/{network_id}", controller=controller, json_body=patch
        )
        return self._normalize_network(data) if isinstance(data, dict) else {}

    async def delete_network(self, network_id: str, controller: str | None = None) -> bool:
        """Delete a network / VLAN by id (Integration API)."""
        site_id = await self._resolve_integration_site_id(controller)
        await self._integration_request("delete", f"sites/{site_id}/networks/{network_id}", controller=controller)
        return True
