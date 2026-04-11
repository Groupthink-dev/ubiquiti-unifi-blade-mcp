"""Ubiquiti UniFi Blade MCP Server — device monitoring, client visibility, firewall state, and network security.

Wraps the ``aiounifi`` library as MCP tools. Token-efficient by default:
compact output, null-field omission, one line per item.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

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
    format_port_forwards,
    format_sites,
    format_traffic_routes,
    format_traffic_rules,
    format_wlan_list,
)
from ubiquiti_unifi_blade_mcp.models import require_write

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
        "Multi-controller support — pass controller= to target a specific controller. "
        "Write operations (block/unblock, WLAN toggle, restart) require UNIFI_WRITE_ENABLED=true."
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


# ===========================================================================
# Entry point
# ===========================================================================


def main() -> None:
    """Run the MCP server."""
    if TRANSPORT == "http":
        import uvicorn

        from ubiquiti_unifi_blade_mcp.auth import BearerAuthMiddleware

        app = mcp.http_app()
        app.add_middleware(BearerAuthMiddleware)
        uvicorn.run(app, host=HTTP_HOST, port=HTTP_PORT)
    else:
        mcp.run(transport="stdio")
