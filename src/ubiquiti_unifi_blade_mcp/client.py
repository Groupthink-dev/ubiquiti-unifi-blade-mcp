"""UniFi controller client wrapper.

Wraps ``aiounifi`` with credential scrubbing, multi-controller support,
and session management. All methods are async — aiounifi is natively async.
"""

from __future__ import annotations

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

# Patterns to scrub from error messages
_CREDENTIAL_PATTERNS = [
    re.compile(r"password[=:]\S+", re.IGNORECASE),
    re.compile(r"cookie[=:]\S+", re.IGNORECASE),
    re.compile(r"x-csrf-token[=:]\S+", re.IGNORECASE),
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

    async def _get_controller(self, controller: str | None = None) -> Controller:
        """Get or create an aiounifi Controller for the given controller."""
        name = controller or self._configs[0].name
        if name in self._controllers and name in self._connected:
            return self._controllers[name]

        config = self._get_config(name)

        # Create SSL context
        ssl_context: ssl.SSLContext | Literal[False] = False
        if config.verify_ssl:
            ssl_context = ssl.create_default_context()

        # Create aiohttp session
        if name not in self._sessions or self._sessions[name].closed:
            self._sessions[name] = aiohttp.ClientSession()

        # Create aiounifi configuration
        unifi_config = Configuration(
            session=self._sessions[name],
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
