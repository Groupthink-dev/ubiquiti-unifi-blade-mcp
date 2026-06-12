"""Shared constants, types, and gates for Ubiquiti UniFi Blade MCP server."""

from __future__ import annotations

import copy
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

# Server-managed read-only keys present in a GET network object that the
# Integration-API PUT rejects ("Unknown request body property '$.<key>'").
# merge_network_update() strips these from the read-merged body before PUT.
_NETWORK_READONLY_KEYS = ("id", "metadata", "default")

# Generalised strip-set for ALL Integration-API resources (AUD-04-41): the
# live-verified networks set (id/metadata/default — Network 10.x rejects each
# when echoed back, paddington 2026-06-06) plus the documented Integration-API
# server-managed metadata keys that GET responses carry but PUT bodies must not:
# creation/update timestamps and statistics counters.
_RESOURCE_READONLY_KEYS = _NETWORK_READONLY_KEYS + (
    "createdAt",
    "updatedAt",
    "statistics",
)


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
    lease_seconds: int = 86400,
    domain_name: str = "",
    dhcp_mode: str = "server",
    ping_conflict: bool = True,
    isolated: bool = False,
    internet_access: bool = True,
    zone_id: str | None = None,
) -> dict[str, object]:
    """Assemble an Integration-API ``networks`` payload from flat tool arguments.

    Returns the body for ``POST /proxy/network/integration/v1/sites/{id}/networks``,
    matching the live Network 10.x Integration-API schema (captured 2026-06-06):

    - **UNMANAGED** (``purpose='vlan-only'``): ``{management, name, enabled, vlanId}``
      — a VLAN tag with no L3. Verified live (create→delete) on Network 10.x.
    - **GATEWAY** (``purpose='corporate'/'guest'``): the above plus required
      non-null scalars (``isolationEnabled``, ``cellularBackupEnabled``,
      ``internetAccessEnabled``) and a nested ``ipv4Configuration``
      (``autoScaleEnabled`` + ``hostIpAddress`` + ``prefixLength``, optional
      ``dhcpConfiguration`` with ``mode=SERVER`` + ``ipAddressRange`` +
      ``leaseTimeSeconds`` + ``pingConflictDetectionEnabled``). Verified live
      (create→delete with DHCP) on Network 10.x; the API rejects null on any of
      those required fields. Conservative defaults are applied for the scalars.

    This builder is the single adjustment point — callers and tests read its output.

    Optional DHCP/L3 knobs (GATEWAY only) each default to today's hardcoded
    constant so omission is byte-identical to the prior behaviour:
    ``lease_seconds`` (DHCP lease, default 86400), ``domain_name`` (DHCP search
    domain — omitted on ``""``), ``dhcp_mode`` (``"server"`` | ``"none"``;
    ``"none"`` suppresses the ``dhcpConfiguration`` even when a range is given —
    relay is DEFERRED, OQ-3), ``ping_conflict``, ``isolated`` (was hardcoded
    ``False``), and ``internet_access`` (was hardcoded ``True``). DNS-server
    plumbing is intentionally NOT exposed in Phase A — the wire shape
    (``dnsServer1/2/3`` scalar vs array) is unconfirmed (OQ-2) and deferred to
    the live-verify phase rather than guessed.
    """
    management = _MANAGEMENT_BY_PURPOSE.get((purpose or "").strip().lower(), "GATEWAY")
    spec: dict[str, object] = {"management": management, "name": name, "enabled": enabled}
    if vlan_id is not None:
        spec["vlanId"] = vlan_id
    if zone_id:
        spec["zoneId"] = zone_id

    if management == "UNMANAGED":
        # VLAN-only networks carry no L3 configuration — nothing further to add.
        return spec

    # GATEWAY (routed) networks require these scalar fields on create — the API
    # rejects null (verified live on Network 10.x 2026-06-06: "isolationEnabled
    # must not be null", etc.). Conservative defaults for a new network.
    spec["isolationEnabled"] = isolated
    spec["cellularBackupEnabled"] = False
    spec["internetAccessEnabled"] = internet_access

    host_ip, prefix = _parse_host_and_prefix(subnet, gateway)
    if host_ip and prefix is not None:
        ipv4: dict[str, object] = {
            "autoScaleEnabled": False,  # required, non-null
            "hostIpAddress": host_ip,
            "prefixLength": prefix,
        }
        # dhcp_mode == "none" suppresses the dhcpConfiguration even when a range
        # is supplied (relay is DEFERRED — OQ-3, not in this phase).
        if dhcp_start and dhcp_stop and (dhcp_mode or "").strip().lower() != "none":
            # leaseTimeSeconds + pingConflictDetectionEnabled are required (non-null)
            # whenever a dhcpConfiguration is present.
            dhcp: dict[str, object] = {
                "mode": "SERVER",
                "ipAddressRange": {"start": dhcp_start, "stop": dhcp_stop},
                "leaseTimeSeconds": lease_seconds,
                "pingConflictDetectionEnabled": ping_conflict,
            }
            # domainName is a live-confirmed dhcpConfiguration key; omit on "" to
            # preserve current bytes.
            if domain_name:
                dhcp["domainName"] = domain_name
            ipv4["dhcpConfiguration"] = dhcp
        spec["ipv4Configuration"] = ipv4
    return spec


def merge_network_update(base: dict[str, object], changes: dict[str, object]) -> dict[str, object]:
    """Deep-merge supplied ``changes`` into a fetched network object (read-merge-write).

    The Integration-API ``PUT`` replaces the whole object, so a blind partial PUT
    wipes everything not re-sent — the /16→/24 DHCP-loss bug DD-383 fixes. This
    helper deep-copies ``base`` (the un-normalized object from ``integration_get``,
    preserving server-managed keys like ``mdnsForwardingEnabled``/``metadata``/
    zone) and overlays ONLY the supplied fields.

    Recognized ``changes`` keys (anything else is ignored — this is not a
    pass-through):

    - Top-level scalars: ``name``, ``vlanId``, ``enabled``, ``isolationEnabled``,
      ``internetAccessEnabled``.
    - L3: ``subnet`` (CIDR-with-host) and/or ``gateway`` translate to nested
      ``ipv4Configuration.hostIpAddress`` / ``prefixLength`` the same way create
      does (``_parse_host_and_prefix``); the legacy flat ``ipSubnet``/``gatewayIp``
      keys are NOT emitted.
    - DHCP (merged into ``ipv4Configuration.dhcpConfiguration`` without replacing
      it): ``dhcp_start``/``dhcp_stop`` → ``ipAddressRange.start``/``stop``;
      ``leaseTimeSeconds``, ``pingConflictDetectionEnabled``, ``domainName``.

    Nested dicts are merged, not replaced, so editing only the prefix preserves
    the existing DHCP range/lease and the server-managed keys.
    """
    merged = copy.deepcopy(base)

    for key in ("name", "vlanId", "enabled", "isolationEnabled", "internetAccessEnabled"):
        if key in changes:
            merged[key] = changes[key]

    host_ip, prefix = _parse_host_and_prefix(
        changes.get("subnet"),  # type: ignore[arg-type]
        changes.get("gateway"),  # type: ignore[arg-type]
    )
    dhcp_changes = {
        api_key: changes[chg_key]
        for chg_key, api_key in (
            ("dhcp_start", "ipAddressRange.start"),
            ("dhcp_stop", "ipAddressRange.stop"),
            ("leaseTimeSeconds", "leaseTimeSeconds"),
            ("pingConflictDetectionEnabled", "pingConflictDetectionEnabled"),
            ("domainName", "domainName"),
        )
        if chg_key in changes
    }

    if host_ip is not None or prefix is not None or dhcp_changes:
        ipv4 = merged.get("ipv4Configuration")
        if not isinstance(ipv4, dict):
            ipv4 = {}
        if host_ip is not None:
            ipv4["hostIpAddress"] = host_ip
        if prefix is not None:
            ipv4["prefixLength"] = prefix
        if dhcp_changes:
            dhcp = ipv4.get("dhcpConfiguration")
            if not isinstance(dhcp, dict):
                dhcp = {}
            for api_key, value in dhcp_changes.items():
                if api_key.startswith("ipAddressRange."):
                    rng = dhcp.get("ipAddressRange")
                    if not isinstance(rng, dict):
                        rng = {}
                    rng[api_key.split(".", 1)[1]] = value
                    dhcp["ipAddressRange"] = rng
                else:
                    dhcp[api_key] = value
            ipv4["dhcpConfiguration"] = dhcp
        merged["ipv4Configuration"] = ipv4

    # The Integration-API PUT replaces the whole object but REJECTS server-managed
    # read-only keys echoed back in the body (live Network 10.x: 400
    # api.request.unknown-property "Unknown request body property '$.id'", then
    # '$.metadata', then '$.default'). The GET we merge from carries them, so strip
    # them before PUT. (mdnsForwardingEnabled IS mutable — keep it.) Verified live
    # on paddington 2026-06-06; the mocked suite could not surface this — see DD-382.
    for ro_key in _NETWORK_READONLY_KEYS:
        merged.pop(ro_key, None)

    return merged


def _deep_merge_dicts(base: dict[str, object], overlay: dict[str, object]) -> dict[str, object]:
    """Recursively overlay ``overlay`` onto ``base`` in place and return ``base``.

    Nested dicts merge key-by-key; everything else (scalars, lists) replaces —
    matching the merge semantics :func:`merge_network_update` applies to
    ``ipv4Configuration``/``dhcpConfiguration``.
    """
    for key, value in overlay.items():
        existing = base.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            _deep_merge_dicts(existing, value)
        else:
            base[key] = value
    return base


def merge_resource_update(base: dict[str, object], changes: dict[str, object]) -> dict[str, object]:
    """Deep-merge a partial ``changes`` body over a fetched resource object (read-merge-write).

    The Integration-API ``PUT`` replaces the whole object, so a blind partial PUT
    wipes every field not re-sent — the DD-383 DHCP-wipe class, previously fixed
    only for ``networks`` (AUD-04-41 generalises it to all writable resources:
    firewall policies, WLANs, ACL rules, DNS policies, traffic-matching lists,
    vouchers). Unlike :func:`merge_network_update` this is a raw pass-through
    overlay — caller keys are the wire-schema keys, nothing is translated.
    Nested dicts merge (unspecified siblings survive); scalars and lists replace.

    The server-managed read-only keys (``_RESOURCE_READONLY_KEYS``) are stripped
    from the merged body — the live PUT 400s on echoed read-only keys ("Unknown
    request body property"), so without the strip even a full GET→edit→PUT
    round-trip is rejected. Neither input is mutated.
    """
    merged = _deep_merge_dicts(copy.deepcopy(base), copy.deepcopy(changes))
    for ro_key in _RESOURCE_READONLY_KEYS:
        merged.pop(ro_key, None)
    return merged


def is_write_enabled() -> bool:
    """Check if write operations are enabled via env var."""
    return os.environ.get("UNIFI_WRITE_ENABLED", "").lower() == "true"


def require_write() -> str | None:
    """Return an error message if writes are disabled, else None."""
    if not is_write_enabled():
        return "Error: Write operations are disabled. Set UNIFI_WRITE_ENABLED=true to enable."
    return None
