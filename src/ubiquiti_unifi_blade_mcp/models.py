"""Shared constants, types, and gates for Ubiquiti UniFi Blade MCP server."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Default limits for list operations (token efficiency)
DEFAULT_CLIENT_LIMIT = 50
DEFAULT_DEVICE_LIMIT = 30
DEFAULT_EVENT_LIMIT = 20


@dataclass
class ControllerConfig:
    """Configuration for a single UniFi controller."""

    name: str
    host: str
    username: str
    password: str
    port: int = 443
    site: str = "default"
    verify_ssl: bool = False
    totp_secret: str = ""
    api_key: str = ""

    @property
    def auth_mode(self) -> str:
        """Return ``"apikey"`` when an Integration API key is set, else ``"session"``.

        The two modes map to two endpoint families: session (username/password +
        cookie/CSRF) drives the legacy ``/api/s/...`` controller API used by the
        monitoring tools via aiounifi; ``apikey`` (``X-API-KEY``) drives the
        official stateless Integration API (``/proxy/network/integration/v1/...``)
        used by the network/VLAN tools.
        """
        return "apikey" if self.api_key else "session"


def parse_controllers() -> list[ControllerConfig]:
    """Parse UniFi controller configuration from environment variables.

    Supports two modes:

    1. Multi-controller: ``UNIFI_CONTROLLERS=home,office`` with per-controller
       ``UNIFI_HOME_HOST``, ``UNIFI_HOME_USERNAME``, ``UNIFI_HOME_PASSWORD``

    2. Single-controller (default): ``UNIFI_HOST``, ``UNIFI_USERNAME``,
       ``UNIFI_PASSWORD`` treated as controller "default".
    """
    controllers_str = os.environ.get("UNIFI_CONTROLLERS", "").strip()
    if controllers_str:
        controllers = []
        for name in controllers_str.split(","):
            name = name.strip()
            prefix = f"UNIFI_{name.upper()}_"
            host = os.environ.get(f"{prefix}HOST", "")
            username = os.environ.get(f"{prefix}USERNAME", "")
            password = os.environ.get(f"{prefix}PASSWORD", "")
            api_key = os.environ.get(f"{prefix}API_KEY", "")
            # A controller is usable with EITHER session creds (username+password)
            # OR an Integration API key. The two unlock different tool families.
            if not host or not ((username and password) or api_key):
                logger.warning("Incomplete config for controller %s — skipping", name)
                continue
            controllers.append(
                ControllerConfig(
                    name=name,
                    host=host,
                    username=username,
                    password=password,
                    port=int(os.environ.get(f"{prefix}PORT", "443")),
                    site=os.environ.get(f"{prefix}SITE", "default"),
                    verify_ssl=os.environ.get(f"{prefix}VERIFY_SSL", "false").lower() == "true",
                    totp_secret=os.environ.get(f"{prefix}TOTP_SECRET", ""),
                    api_key=api_key,
                )
            )
        if not controllers:
            raise ValueError("UNIFI_CONTROLLERS set but no controllers configured correctly")
        return controllers

    # Single-controller mode
    host = os.environ.get("UNIFI_HOST", "")
    username = os.environ.get("UNIFI_USERNAME", "")
    password = os.environ.get("UNIFI_PASSWORD", "")
    api_key = os.environ.get("UNIFI_API_KEY", "")
    if not host or not ((username and password) or api_key):
        raise ValueError(
            "UniFi credentials not configured. Set UNIFI_HOST plus either "
            "UNIFI_USERNAME + UNIFI_PASSWORD (monitoring tools) or UNIFI_API_KEY "
            "(network/VLAN tools via the Integration API)."
        )
    return [
        ControllerConfig(
            name="default",
            host=host,
            username=username,
            password=password,
            port=int(os.environ.get("UNIFI_PORT", "443")),
            site=os.environ.get("UNIFI_SITE", "default"),
            verify_ssl=os.environ.get("UNIFI_VERIFY_SSL", "false").lower() == "true",
            totp_secret=os.environ.get("UNIFI_TOTP_SECRET", ""),
            api_key=api_key,
        )
    ]


def network_spec_from_args(
    name: str,
    vlan_id: int | None,
    *,
    subnet: str | None = None,
    gateway: str | None = None,
    dhcp_start: str | None = None,
    dhcp_stop: str | None = None,
    purpose: str = "corporate",
    enabled: bool = True,
) -> dict[str, object]:
    """Assemble an Integration-API ``networks`` payload from flat tool arguments.

    Returns the camelCase body for ``POST /proxy/network/integration/v1/sites/{id}/networks``.

    NOTE (Phase 0): the exact field names for a *routed/corporate* VLAN on
    Network 10.4.x must be confirmed against the on-console Integration API
    schema (Settings → Control Plane → Integrations). Community docs firmly
    establish only the UNMANAGED shape (``{management, name, enabled, vlanId}``).
    This builder is the single adjustment point — update the keys here once the
    live schema is captured; callers and tests do not change.
    """
    spec: dict[str, object] = {"name": name, "enabled": enabled}
    if vlan_id is not None:
        spec["vlanId"] = vlan_id
    if purpose:
        spec["purpose"] = purpose
    if subnet:
        spec["ipSubnet"] = subnet
    if gateway:
        spec["gatewayIp"] = gateway
    if dhcp_start and dhcp_stop:
        spec["dhcpEnabled"] = True
        spec["dhcpStart"] = dhcp_start
        spec["dhcpStop"] = dhcp_stop
    return spec


def is_write_enabled() -> bool:
    """Check if write operations are enabled via env var."""
    return os.environ.get("UNIFI_WRITE_ENABLED", "").lower() == "true"


def require_write() -> str | None:
    """Return an error message if writes are disabled, else None."""
    if not is_write_enabled():
        return "Error: Write operations are disabled. Set UNIFI_WRITE_ENABLED=true to enable."
    return None
