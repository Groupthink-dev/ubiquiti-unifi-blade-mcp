"""Ubiquiti UniFi Blade MCP Server — device monitoring, client visibility, firewall state, and network security.

Wraps the ``aiounifi`` library as MCP tools. Token-efficient by default:
compact output, null-field omission, one line per item.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from ubiquiti_unifi_blade_mcp.client import UniFiClient, UniFiError
from ubiquiti_unifi_blade_mcp.formatters import (
    format_client_detail,
    format_client_list,
    format_device_detail,
    format_device_list,
    format_dpi,
    format_firewall_policies,
    format_info,
    format_network_detail,
    format_network_list,
    format_port_forwards,
    format_resource_detail,
    format_resource_list,
    format_sites,
    format_traffic_routes,
    format_traffic_rules,
    format_wlan_list,
)
from ubiquiti_unifi_blade_mcp.models import network_spec_from_args, require_write

# Integration-API resources reachable via the generic resource tools (X-API-KEY).
# Mirrors client._INTEGRATION_RESOURCES; read-only ones reject create/update/delete.
ResourceName = Literal[
    "networks",
    "wifi",
    "firewall_policies",
    "firewall_zones",
    "acl_rules",
    "dns_policies",
    "traffic_matching_lists",
    "vouchers",
    "wan_interfaces",
    "radius_profiles",
    "vpn_servers",
    "vpn_tunnels",
    "device_tags",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

log_level = os.environ.get("UNIFI_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.WARNING))

# ---------------------------------------------------------------------------
# Transport configuration
# ---------------------------------------------------------------------------

TRANSPORT = os.environ.get("UNIFI_MCP_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("UNIFI_MCP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("UNIFI_MCP_PORT", "8781"))

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "UniFiBlade",
    instructions=(
        "Ubiquiti UniFi network operations. Monitor devices, view clients, "
        "inspect firewall policies, check traffic routes, and manage WLANs. "
        "Manage networks/VLANs (list/create/update/delete) via the official "
        "Integration API — these tools require an API key (UNIFI_API_KEY). "
        "Multi-controller support — pass controller= to target a specific controller. "
        "Write operations (block/unblock, WLAN toggle, restart, network create/update/delete) "
        "require UNIFI_WRITE_ENABLED=true; destructive ones also require confirm=true."
    ),
)

# Lazy-initialized client
_client: UniFiClient | None = None


def _get_client() -> UniFiClient:
    """Get or create the UniFiClient singleton."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = UniFiClient()
    return _client


def _error_response(e: UniFiError) -> str:
    """Format a client error as a user-friendly string."""
    return f"Error: {e}"


# ===========================================================================
# INFO & SITES
# ===========================================================================


@mcp.tool()
async def unifi_info(
    controller: Annotated[str | None, Field(description="Controller name (omit for all controllers)")] = None,
) -> str:
    """Health check: controller version, hostname, site, device count, client count, write gate."""
    try:
        info = await _get_client().info(controller)
        return format_info(info)
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_sites(
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """List sites on the controller."""
    try:
        sites = await _get_client().get_sites(controller)
        return format_sites(sites)
    except UniFiError as e:
        return _error_response(e)


# ===========================================================================
# NETWORKS / VLANs  (Integration API — requires UNIFI_API_KEY)
# ===========================================================================


@mcp.tool()
async def unifi_networks(
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """List networks/VLANs: name, VLAN id, enabled/disabled, purpose, subnet. Requires UNIFI_API_KEY."""
    try:
        networks = await _get_client().get_networks(controller)
        return format_network_list(networks)
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_network(
    network_id: Annotated[str, Field(description="Network ID (from unifi_networks)")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Full detail for a single network/VLAN: VLAN id, subnet, gateway, purpose. Requires UNIFI_API_KEY."""
    try:
        network = await _get_client().get_network(network_id, controller)
        if network is None:
            return f"Error: Network {network_id} not found"
        return format_network_detail(network)
    except UniFiError as e:
        return _error_response(e)


# ===========================================================================
# DEVICES
# ===========================================================================


@mcp.tool()
async def unifi_devices(
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """List all network devices (APs, switches, gateways) with status, model, clients, uptime, firmware."""
    try:
        devices = await _get_client().get_devices(controller)
        return format_device_list(devices)
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_device(
    mac: Annotated[str, Field(description="Device MAC address (from unifi_devices)")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Full detail for a single device: model, firmware, uptime, port table with PoE, client count."""
    try:
        device = await _get_client().get_device(mac, controller)
        if device is None:
            return f"Error: Device {mac} not found"
        return format_device_detail(device)
    except UniFiError as e:
        return _error_response(e)


# ===========================================================================
# CLIENTS
# ===========================================================================


@mcp.tool()
async def unifi_clients(
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """List connected clients: name, IP, SSID/wired, signal, experience score, blocked status."""
    try:
        clients = await _get_client().get_clients(controller)
        return format_client_list(clients)
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_client(
    mac: Annotated[str, Field(description="Client MAC address (from unifi_clients)")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Full detail for a single client: IP, network, SSID, signal, experience, TX/RX, vendor, AP."""
    try:
        client = await _get_client().get_client(mac, controller)
        if client is None:
            return f"Error: Client {mac} not found"
        return format_client_detail(client)
    except UniFiError as e:
        return _error_response(e)


# ===========================================================================
# WLANs
# ===========================================================================


@mcp.tool()
async def unifi_wlans(
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """List all WLANs (SSIDs): name, enabled/disabled, security type, guest flag."""
    try:
        wlans = await _get_client().get_wlans(controller)
        return format_wlan_list(wlans)
    except UniFiError as e:
        return _error_response(e)


# ===========================================================================
# FIREWALL & SECURITY (read)
# ===========================================================================


@mcp.tool()
async def unifi_firewall(
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Firewall policies: name, enabled/disabled, action, source/destination zones."""
    try:
        policies = await _get_client().get_firewall_policies(controller)
        return format_firewall_policies(policies)
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_traffic_routes(
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Traffic routes: description, enabled/disabled, matching target."""
    try:
        routes = await _get_client().get_traffic_routes(controller)
        return format_traffic_routes(routes)
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_traffic_rules(
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Traffic rules: description, enabled/disabled, action, matching target."""
    try:
        rules = await _get_client().get_traffic_rules(controller)
        return format_traffic_rules(rules)
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_port_forwards(
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Port forwarding rules: name, enabled/disabled, protocol, external → internal mapping."""
    try:
        forwards = await _get_client().get_port_forwards(controller)
        return format_port_forwards(forwards)
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_dpi(
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """DPI restriction groups and apps: name, enabled/disabled."""
    try:
        dpi = await _get_client().get_dpi_restrictions(controller)
        return format_dpi(dpi)
    except UniFiError as e:
        return _error_response(e)


# ===========================================================================
# WRITE OPERATIONS (gated by UNIFI_WRITE_ENABLED=true)
# ===========================================================================


@mcp.tool()
async def unifi_block_client(
    mac: Annotated[str, Field(description="Client MAC address to block")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
    confirm: Annotated[bool, Field(description="Must be true to confirm — blocks client from network")] = False,
) -> str:
    """Block a client from the network. Requires UNIFI_WRITE_ENABLED=true and confirm=true."""
    gate = require_write()
    if gate:
        return gate
    if not confirm:
        return "Error: Set confirm=true to block this client."
    try:
        await _get_client().block_client(mac, controller)
        return f"Blocked client {mac}"
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_unblock_client(
    mac: Annotated[str, Field(description="Client MAC address to unblock")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Unblock a previously blocked client. Requires UNIFI_WRITE_ENABLED=true."""
    gate = require_write()
    if gate:
        return gate
    try:
        await _get_client().unblock_client(mac, controller)
        return f"Unblocked client {mac}"
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_reconnect_client(
    mac: Annotated[str, Field(description="Client MAC address to reconnect")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Force a wireless client to reconnect. Requires UNIFI_WRITE_ENABLED=true."""
    gate = require_write()
    if gate:
        return gate
    try:
        await _get_client().reconnect_client(mac, controller)
        return f"Reconnecting client {mac}"
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_toggle_wlan(
    wlan_id: Annotated[str, Field(description="WLAN ID (from unifi_wlans)")],
    enable: Annotated[bool, Field(description="True to enable, false to disable")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Enable or disable a WLAN (SSID). Requires UNIFI_WRITE_ENABLED=true."""
    gate = require_write()
    if gate:
        return gate
    try:
        if enable:
            await _get_client().enable_wlan(wlan_id, controller)
            return f"Enabled WLAN {wlan_id}"
        else:
            await _get_client().disable_wlan(wlan_id, controller)
            return f"Disabled WLAN {wlan_id}"
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_toggle_traffic_route(
    route_id: Annotated[str, Field(description="Traffic route ID (from unifi_traffic_routes)")],
    enable: Annotated[bool, Field(description="True to enable, false to disable")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Enable or disable a traffic route. Requires UNIFI_WRITE_ENABLED=true."""
    gate = require_write()
    if gate:
        return gate
    try:
        if enable:
            await _get_client().enable_traffic_route(route_id, controller)
            return f"Enabled traffic route {route_id}"
        else:
            await _get_client().disable_traffic_route(route_id, controller)
            return f"Disabled traffic route {route_id}"
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_restart_device(
    mac: Annotated[str, Field(description="Device MAC address (from unifi_devices)")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
    confirm: Annotated[
        bool,
        Field(description="Must be true to confirm — device will be offline during restart"),
    ] = False,
) -> str:
    """Restart a network device (AP, switch, gateway). Requires UNIFI_WRITE_ENABLED=true and confirm=true."""
    gate = require_write()
    if gate:
        return gate
    if not confirm:
        return "Error: Set confirm=true to restart. Device will be offline during restart."
    try:
        await _get_client().restart_device(mac, controller)
        return f"Restarting device {mac}"
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_create_network(
    name: Annotated[str, Field(description="Network name (e.g. 'Services')")],
    vlan_id: Annotated[int, Field(description="VLAN ID (e.g. 40); use 0 for the default/untagged network")],
    subnet: Annotated[str | None, Field(description="CIDR with gateway host, e.g. '10.1.40.254/24'")] = None,
    gateway: Annotated[str | None, Field(description="Gateway IP, e.g. '10.1.40.254'")] = None,
    dhcp_start: Annotated[str | None, Field(description="DHCP range start, e.g. '10.1.40.100'")] = None,
    dhcp_stop: Annotated[str | None, Field(description="DHCP range end, e.g. '10.1.40.200'")] = None,
    purpose: Annotated[str, Field(description="Network purpose (corporate, guest, vlan-only)")] = "corporate",
    enabled: Annotated[bool, Field(description="Whether the network is enabled")] = True,
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
    confirm: Annotated[bool, Field(description="Must be true to confirm — creates a network/VLAN")] = False,
) -> str:
    """Create a network/VLAN. Requires UNIFI_API_KEY, UNIFI_WRITE_ENABLED=true and confirm=true."""
    gate = require_write()
    if gate:
        return gate
    if not confirm:
        return "Error: Set confirm=true to create this network/VLAN."
    try:
        spec = network_spec_from_args(
            name,
            vlan_id,
            subnet=subnet,
            gateway=gateway,
            dhcp_start=dhcp_start,
            dhcp_stop=dhcp_stop,
            purpose=purpose,
            enabled=enabled,
        )
        net = await _get_client().create_network(spec, controller)
        return f"Created network '{name}' (vlan {vlan_id})\n{format_network_detail(net)}"
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_update_network(
    network_id: Annotated[str, Field(description="Network ID (from unifi_networks)")],
    name: Annotated[str | None, Field(description="New name")] = None,
    vlan_id: Annotated[int | None, Field(description="New VLAN ID")] = None,
    subnet: Annotated[str | None, Field(description="New CIDR, e.g. '10.1.40.254/24'")] = None,
    gateway: Annotated[str | None, Field(description="New gateway IP")] = None,
    enabled: Annotated[bool | None, Field(description="Enable/disable the network")] = None,
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
    confirm: Annotated[bool, Field(description="Must be true to confirm — modifies a network/VLAN")] = False,
) -> str:
    """Update a network/VLAN (only supplied fields). Requires UNIFI_API_KEY, UNIFI_WRITE_ENABLED=true, confirm=true."""
    gate = require_write()
    if gate:
        return gate
    if not confirm:
        return "Error: Set confirm=true to update this network/VLAN."
    patch: dict[str, object] = {}
    if name is not None:
        patch["name"] = name
    if vlan_id is not None:
        patch["vlanId"] = vlan_id
    if subnet is not None:
        patch["ipSubnet"] = subnet
    if gateway is not None:
        patch["gatewayIp"] = gateway
    if enabled is not None:
        patch["enabled"] = enabled
    if not patch:
        return "Error: No fields to update — supply at least one of name/vlan_id/subnet/gateway/enabled."
    try:
        net = await _get_client().update_network(network_id, patch, controller)
        return f"Updated network {network_id}\n{format_network_detail(net)}"
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_delete_network(
    network_id: Annotated[str, Field(description="Network ID (from unifi_networks)")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
    confirm: Annotated[bool, Field(description="Must be true to confirm — permanently deletes the network")] = False,
) -> str:
    """Delete a network/VLAN. Requires UNIFI_API_KEY, UNIFI_WRITE_ENABLED=true and confirm=true."""
    gate = require_write()
    if gate:
        return gate
    if not confirm:
        return "Error: Set confirm=true to delete this network/VLAN. This is permanent."
    try:
        await _get_client().delete_network(network_id, controller)
        return f"Deleted network {network_id}"
    except UniFiError as e:
        return _error_response(e)


# ===========================================================================
# GENERIC INTEGRATION-API RESOURCES (X-API-KEY)
# ===========================================================================
# Cover the official resources beyond networks: WLANs (wifi), firewall
# policies/zones, ACL rules, DNS policies, traffic-matching lists, vouchers,
# plus read-only reference data (WANs, RADIUS, VPN, device tags). Writes take a
# raw JSON `body` per the on-console v10.x schema (confirm via Settings →
# Control Plane → Integrations). All require UNIFI_API_KEY.


@mcp.tool()
async def unifi_resource_list(
    resource: Annotated[ResourceName, Field(description="Integration-API resource to list")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """List items of an Integration-API resource (wifi, firewall_policies, acl_rules, dns_policies, vouchers, …).

    Requires UNIFI_API_KEY.
    """
    try:
        items = await _get_client().integration_list(resource, controller)
        return format_resource_list(items, resource)
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_resource_get(
    resource: Annotated[ResourceName, Field(description="Integration-API resource")],
    item_id: Annotated[str, Field(description="Item id (from unifi_resource_list)")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
) -> str:
    """Full detail for one Integration-API resource item. Requires UNIFI_API_KEY."""
    try:
        item = await _get_client().integration_get(resource, item_id, controller)
        if item is None:
            return f"Error: {resource} {item_id} not found"
        return format_resource_detail(item)
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_resource_create(
    resource: Annotated[ResourceName, Field(description="Integration-API resource (must be writable)")],
    body: Annotated[
        dict[str, Any],
        Field(description="Raw JSON body per the v10.x Integration-API schema for this resource"),
    ],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
    confirm: Annotated[bool, Field(description="Must be true to confirm the create")] = False,
) -> str:
    """Create an Integration-API resource item from a raw body.

    Requires UNIFI_API_KEY, UNIFI_WRITE_ENABLED=true, confirm=true.
    """
    gate = require_write()
    if gate:
        return gate
    if not confirm:
        return f"Error: Set confirm=true to create this {resource} item."
    try:
        created = await _get_client().integration_create(resource, body, controller)
        return f"Created {resource} item\n{format_resource_detail(created)}"
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_resource_update(
    resource: Annotated[ResourceName, Field(description="Integration-API resource (must be writable)")],
    item_id: Annotated[str, Field(description="Item id (from unifi_resource_list)")],
    body: Annotated[
        dict[str, Any],
        Field(description="Raw JSON body (PUT) per the v10.x Integration-API schema for this resource"),
    ],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
    confirm: Annotated[bool, Field(description="Must be true to confirm the update")] = False,
) -> str:
    """Update (PUT) an Integration-API resource item. Requires UNIFI_API_KEY, UNIFI_WRITE_ENABLED=true, confirm=true."""
    gate = require_write()
    if gate:
        return gate
    if not confirm:
        return f"Error: Set confirm=true to update this {resource} item."
    try:
        updated = await _get_client().integration_update(resource, item_id, body, controller)
        return f"Updated {resource} {item_id}\n{format_resource_detail(updated)}"
    except UniFiError as e:
        return _error_response(e)


@mcp.tool()
async def unifi_resource_delete(
    resource: Annotated[ResourceName, Field(description="Integration-API resource (must be writable)")],
    item_id: Annotated[str, Field(description="Item id (from unifi_resource_list)")],
    controller: Annotated[str | None, Field(description="Controller name (omit for default)")] = None,
    confirm: Annotated[bool, Field(description="Must be true to confirm — permanent")] = False,
) -> str:
    """Delete an Integration-API resource item. Requires UNIFI_API_KEY, UNIFI_WRITE_ENABLED=true, confirm=true."""
    gate = require_write()
    if gate:
        return gate
    if not confirm:
        return f"Error: Set confirm=true to delete this {resource} item. This is permanent."
    try:
        await _get_client().integration_delete(resource, item_id, controller)
        return f"Deleted {resource} {item_id}"
    except UniFiError as e:
        return _error_response(e)


# ===========================================================================
# Entry point
# ===========================================================================


def main() -> None:
    """Run the MCP server."""
    if TRANSPORT == "http":
        import uvicorn

        from ubiquiti_unifi_blade_mcp.auth import BearerAuthMiddleware, get_bearer_token

        # HTTP transport is a manual loopback path only — never expose it
        # unauthenticated. Require a bearer token when http is explicitly selected.
        if get_bearer_token() is None:
            raise SystemExit(
                "Refusing to start HTTP transport without auth. "
                "Set UNIFI_MCP_API_TOKEN to a non-empty value (the bearer token "
                "clients must send), or use the default stdio transport."
            )

        app = mcp.http_app()
        app.add_middleware(BearerAuthMiddleware)
        uvicorn.run(app, host=HTTP_HOST, port=HTTP_PORT)
    else:
        mcp.run(transport="stdio")
