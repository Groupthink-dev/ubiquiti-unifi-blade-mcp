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


# Friendly ``purpose`` argument → Integration-API ``management`` enum value.
# The Integration API does NOT use the legacy aiounifi "purpose"
# (corporate/guest/vlan-only) string. It keys networks on ``management``, with
# two observed values: ``UNMANAGED`` (a VLAN-only / switch-only tag, no L3) and
# ``GATEWAY`` (a routed L3 network with an ``ipv4Configuration``). Captured live
# against Network 10.x on 2026-06-06. Raw ``management`` values are also accepted.
_MANAGEMENT_BY_PURPOSE = {
    "vlan-only": "UNMANAGED",
    "vlan_only": "UNMANAGED",
    "vlanonly": "UNMANAGED",
    "unmanaged": "UNMANAGED",
    "corporate": "GATEWAY",
    "gateway": "GATEWAY",
    "guest": "GATEWAY",
    "routed": "GATEWAY",
}


def _parse_host_and_prefix(subnet: str | None, gateway: str | None) -> tuple[str | None, int | None]:
    """Resolve (hostIpAddress, prefixLength) from a CIDR ``subnet`` and/or ``gateway``.

    ``subnet`` is the gateway-host CIDR (e.g. ``10.1.40.254/24``): its host part is
    the L3 gateway address and its suffix is the prefix length. An explicit
    ``gateway`` overrides the host part. Returns ``(None, None)`` when no usable
    address/prefix can be derived.
    """
    host_ip = gateway
    prefix: int | None = None
    if subnet:
        ip_part, _, prefix_part = subnet.partition("/")
        if ip_part and host_ip is None:
            host_ip = ip_part.strip()
        if prefix_part.strip().isdigit():
            prefix = int(prefix_part.strip())
    return host_ip, prefix


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

    Returns the body for ``POST /proxy/network/integration/v1/sites/{id}/networks``,
    matching the live Network 10.x Integration-API schema (captured 2026-06-06):

    - **UNMANAGED** (``purpose='vlan-only'``): ``{management, name, enabled, vlanId}``
      — a VLAN tag with no L3. Verified live (create→delete) on Network 10.x.
    - **GATEWAY** (``purpose='corporate'/'guest'``): the above plus a nested
      ``ipv4Configuration`` (``hostIpAddress`` + ``prefixLength``, optional
      ``dhcpConfiguration`` with ``mode=SERVER`` + ``ipAddressRange``). The
      remaining GATEWAY fields seen on reads (``zoneId``, ``internetAccessEnabled``,
      …) are server-defaulted on create. The GATEWAY create payload is best-effort
      pending a live create→delete verification; UNMANAGED is the proven path.

    This builder is the single adjustment point — callers and tests read its output.
    """
    management = _MANAGEMENT_BY_PURPOSE.get((purpose or "").strip().lower(), "GATEWAY")
    spec: dict[str, object] = {"management": management, "name": name, "enabled": enabled}
    if vlan_id is not None:
        spec["vlanId"] = vlan_id

    if management == "UNMANAGED":
        # VLAN-only networks carry no L3 configuration — nothing further to add.
        return spec

    host_ip, prefix = _parse_host_and_prefix(subnet, gateway)
    if host_ip and prefix is not None:
        ipv4: dict[str, object] = {"hostIpAddress": host_ip, "prefixLength": prefix}
        if dhcp_start and dhcp_stop:
            ipv4["dhcpConfiguration"] = {
                "mode": "SERVER",
                "ipAddressRange": {"start": dhcp_start, "stop": dhcp_stop},
            }
        spec["ipv4Configuration"] = ipv4
    return spec


def is_write_enabled() -> bool:
    """Check if write operations are enabled via env var."""
    return os.environ.get("UNIFI_WRITE_ENABLED", "").lower() == "true"


def require_write() -> str | None:
    """Return an error message if writes are disabled, else None."""
    if not is_write_enabled():
        return "Error: Write operations are disabled. Set UNIFI_WRITE_ENABLED=true to enable."
    return None
