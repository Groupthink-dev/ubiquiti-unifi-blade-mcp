"""Token-efficient output formatters for Ubiquiti UniFi Blade MCP server.

All formatters return compact strings optimised for LLM consumption:
- One line per item
- Pipe-delimited fields
- Null-field omission
- Human-readable units
"""

from __future__ import annotations

import json
from typing import Any


def _uptime_human(seconds: int | float | None) -> str:
    """Convert seconds to human-readable uptime."""
    if not seconds:
        return "?"
    s = int(seconds)
    days, s = divmod(s, 86400)
    hours, s = divmod(s, 3600)
    mins, _ = divmod(s, 60)
    if days > 0:
        return f"{days}d{hours}h"
    if hours > 0:
        return f"{hours}h{mins}m"
    return f"{mins}m"


def _bytes_human(value: int | float | None) -> str:
    """Convert bytes to human-readable format."""
    if value is None:
        return "?"
    b = float(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(b) < 1024:
            return f"{b:.1f}{unit}" if unit != "B" else f"{int(b)}{unit}"
        b /= 1024
    return f"{b:.1f}PB"


def _state_str(state: int | None) -> str:
    """Convert UniFi device state int to string."""
    states = {0: "disconnected", 1: "connected", 2: "pending", 4: "upgrading", 5: "provisioning"}
    return states.get(state or 0, f"state={state}")


# ------------------------------------------------------------------
# Info
# ------------------------------------------------------------------


def format_info(info: dict[str, Any]) -> str:
    """Format health check info."""
    lines = []
    for c in info.get("controllers", []):
        status = c.get("status", "unknown")
        name = c.get("controller", "?")
        if status == "connected":
            parts = [
                f"{name}: connected",
                f"v{c.get('version', '?')}",
                f"host={c.get('hostname', '?')}",
                f"site={c.get('site', '?')}",
                f"devices={c.get('devices', 0)}",
                f"clients={c.get('clients', 0)}",
            ]
            lines.append(" | ".join(parts))
        else:
            lines.append(f"{name}: {status} — {c.get('error', 'unknown error')}")
    lines.append(f"Total devices: {info.get('total_devices', 0)}")
    lines.append(f"Total clients: {info.get('total_clients', 0)}")
    lines.append(f"Write enabled: {info.get('write_enabled', False)}")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Devices
# ------------------------------------------------------------------


def format_device_line(dev: dict[str, Any]) -> str:
    """Format a single device as a compact one-line string."""
    parts = [f"{dev.get('name', '?')}"]

    dtype = dev.get("type", "")
    model = dev.get("model", "")
    if dtype:
        parts.append(dtype)
    if model:
        parts.append(f"model={model}")

    ip = dev.get("ip", "")
    if ip:
        parts.append(f"ip={ip}")

    state = dev.get("state")
    parts.append(_state_str(state))

    clients = dev.get("clients", 0)
    if clients:
        parts.append(f"clients={clients}")

    uptime = dev.get("uptime")
    if uptime:
        parts.append(f"up={_uptime_human(uptime)}")

    if dev.get("upgradeable"):
        parts.append("UPGRADE_AVAILABLE")

    parts.append(f"mac={dev.get('mac', '?')}")
    return " | ".join(parts)


def format_device_list(devices: list[dict[str, Any]]) -> str:
    """Format a list of devices as compact lines."""
    if not devices:
        return "(no devices)"
    return "\n".join(format_device_line(d) for d in devices)


def format_device_detail(dev: dict[str, Any]) -> str:
    """Format a single device with full details."""
    lines = []
    lines.append(f"Name: {dev.get('name', '?')}")
    lines.append(f"MAC: {dev.get('mac', '?')}")
    lines.append(f"Model: {dev.get('model', '?')} ({dev.get('model_name', '')})")
    lines.append(f"Type: {dev.get('type', '?')}")
    lines.append(f"IP: {dev.get('ip', '?')}")
    lines.append(f"Firmware: {dev.get('version', '?')}")
    lines.append(f"State: {_state_str(dev.get('state'))}")
    lines.append(f"Adopted: {dev.get('adopted', False)}")
    lines.append(f"Uptime: {_uptime_human(dev.get('uptime'))}")
    lines.append(f"Clients: {dev.get('clients', 0)}")

    if dev.get("upgradeable"):
        lines.append("UPGRADE AVAILABLE")

    ports = dev.get("ports", [])
    if ports:
        lines.append(f"\nPorts ({len(ports)}):")
        for p in ports:
            port_parts = [f"  {p.get('port_idx', '?')}: {p.get('name', '')}"]
            if p.get("up"):
                port_parts.append(f"up @ {p.get('speed', '?')}Mbps")
            else:
                port_parts.append("down")
            if p.get("poe_enable"):
                port_parts.append(f"PoE={p.get('poe_power', '?')}W")
            lines.append(" | ".join(port_parts))

    return "\n".join(lines)


# ------------------------------------------------------------------
# Clients
# ------------------------------------------------------------------


def format_client_line(client: dict[str, Any]) -> str:
    """Format a single client as a compact one-line string."""
    parts = [f"{client.get('name', '?')}"]

    ip = client.get("ip", "")
    if ip:
        parts.append(f"ip={ip}")

    if client.get("is_wired"):
        parts.append("wired")
    else:
        essid = client.get("essid", "")
        if essid:
            parts.append(f"ssid={essid}")
        signal = client.get("signal")
        if signal:
            parts.append(f"rssi={signal}")

    exp = client.get("experience")
    if exp:
        parts.append(f"exp={exp}%")

    if client.get("blocked"):
        parts.append("BLOCKED")

    uptime = client.get("uptime")
    if uptime:
        parts.append(f"up={_uptime_human(uptime)}")

    parts.append(f"mac={client.get('mac', '?')}")
    return " | ".join(parts)


def format_client_list(clients: list[dict[str, Any]]) -> str:
    """Format a list of clients as compact lines."""
    if not clients:
        return "(no clients)"
    return "\n".join(format_client_line(c) for c in clients)


def format_client_detail(client: dict[str, Any]) -> str:
    """Format a single client with full details."""
    lines = []
    lines.append(f"Name: {client.get('name', '?')}")
    lines.append(f"Hostname: {client.get('hostname', '?')}")
    lines.append(f"MAC: {client.get('mac', '?')}")
    lines.append(f"IP: {client.get('ip', '?')}")
    lines.append(f"Network: {client.get('network', '?')}")

    if client.get("is_wired"):
        lines.append("Connection: Wired")
    else:
        lines.append(f"SSID: {client.get('essid', '?')}")
        lines.append(f"Signal: {client.get('signal', '?')} dBm")
        lines.append(f"AP: {client.get('ap_mac', '?')}")

    lines.append(f"Experience: {client.get('experience', '?')}%")
    lines.append(f"Blocked: {client.get('blocked', False)}")
    lines.append(f"Uptime: {_uptime_human(client.get('uptime'))}")
    lines.append(f"TX: {_bytes_human(client.get('tx_bytes'))}")
    lines.append(f"RX: {_bytes_human(client.get('rx_bytes'))}")

    oui = client.get("oui", "")
    if oui:
        lines.append(f"Vendor: {oui}")

    return "\n".join(lines)


# ------------------------------------------------------------------
# WLANs
# ------------------------------------------------------------------


def format_wlan_list(wlans: list[dict[str, Any]]) -> str:
    """Format WLANs as compact lines."""
    if not wlans:
        return "(no WLANs)"
    lines = []
    for w in wlans:
        parts = [w.get("name", "?")]
        parts.append("enabled" if w.get("enabled") else "DISABLED")
        sec = w.get("security", "")
        if sec:
            parts.append(f"security={sec}")
        if w.get("is_guest"):
            parts.append("guest")
        parts.append(f"id={w.get('id', '?')}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


# ------------------------------------------------------------------
# Networks / VLANs
# ------------------------------------------------------------------


def format_network_list(networks: list[dict[str, Any]]) -> str:
    """Format networks / VLANs as compact lines."""
    if not networks:
        return "(no networks)"
    lines = []
    for n in networks:
        parts = [n.get("name", "?")]
        vlan = n.get("vlan")
        if vlan not in (None, ""):
            parts.append(f"vlan={vlan}")
        parts.append("enabled" if n.get("enabled") else "DISABLED")
        purpose = n.get("purpose", "")
        if purpose:
            parts.append(f"purpose={purpose}")
        subnet = n.get("subnet", "")
        if subnet:
            parts.append(f"subnet={subnet}")
        parts.append(f"id={n.get('id', '?')}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_network_detail(net: dict[str, Any]) -> str:
    """Format a single network / VLAN with full details."""
    lines = [f"Name: {net.get('name', '?')}"]
    vlan = net.get("vlan")
    lines.append(f"VLAN: {vlan if vlan not in (None, '') else '?'}")
    lines.append(f"Enabled: {net.get('enabled', False)}")
    purpose = net.get("purpose", "")
    if purpose:
        lines.append(f"Purpose: {purpose}")
    subnet = net.get("subnet", "")
    if subnet:
        lines.append(f"Subnet: {subnet}")
    gateway = net.get("gateway", "")
    if gateway:
        lines.append(f"Gateway: {gateway}")
    lines.append(f"ID: {net.get('id', '?')}")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Generic Integration-API resources (wifi, firewall, acl, dns, vouchers, …)
# ------------------------------------------------------------------

# Field probed (in order) for the leading label of a generic resource line.
_RESOURCE_LABEL_KEYS = ("name", "ssid", "domain", "displayName", "description")
# Compact summary fields appended as key=value when present.
_RESOURCE_SUMMARY_KEYS = ("type", "action", "vlanId", "vlan", "purpose", "management")


def format_resource_list(items: list[dict[str, Any]], resource: str = "") -> str:
    """Generic compact formatter for an Integration-API resource list."""
    if not items:
        return f"(no {resource or 'items'})"
    lines = []
    for it in items:
        label = next((str(it[k]) for k in _RESOURCE_LABEL_KEYS if it.get(k)), None)
        parts = [label or str(it.get("id") or it.get("_id") or "?")]
        for k in _RESOURCE_SUMMARY_KEYS:
            v = it.get(k)
            if v not in (None, ""):
                parts.append(f"{k}={v}")
        if "enabled" in it:
            parts.append("enabled" if it.get("enabled") else "DISABLED")
        iid = it.get("id") or it.get("_id")
        if iid and label:  # avoid printing id twice when it was used as the label
            parts.append(f"id={iid}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_resource_detail(item: dict[str, Any] | None) -> str:
    """Generic detail formatter — one ``key: value`` per line (nested values as compact JSON)."""
    if not item:
        return "(not found)"
    lines = []
    for k, v in item.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, separators=(",", ":"))
        lines.append(f"{k}: {v}")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Firewall & Security
# ------------------------------------------------------------------


def format_firewall_policies(policies: list[dict[str, Any]]) -> str:
    """Format firewall policies as compact lines."""
    if not policies:
        return "(no firewall policies)"
    lines = []
    for p in policies:
        parts = [p.get("name", "?")]
        parts.append("enabled" if p.get("enabled") else "DISABLED")
        action = p.get("action", "")
        if action:
            parts.append(f"action={action}")
        parts.append(f"id={p.get('id', '?')}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_traffic_routes(routes: list[dict[str, Any]]) -> str:
    """Format traffic routes as compact lines."""
    if not routes:
        return "(no traffic routes)"
    lines = []
    for r in routes:
        parts = [r.get("description", "?")]
        parts.append("enabled" if r.get("enabled") else "DISABLED")
        target = r.get("matching_target", "")
        if target:
            parts.append(f"target={target}")
        parts.append(f"id={r.get('id', '?')}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_traffic_rules(rules: list[dict[str, Any]]) -> str:
    """Format traffic rules as compact lines."""
    if not rules:
        return "(no traffic rules)"
    lines = []
    for r in rules:
        parts = [r.get("description", "?")]
        parts.append("enabled" if r.get("enabled") else "DISABLED")
        action = r.get("action", "")
        if action:
            parts.append(f"action={action}")
        parts.append(f"id={r.get('id', '?')}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_port_forwards(forwards: list[dict[str, Any]]) -> str:
    """Format port forwards as compact lines."""
    if not forwards:
        return "(no port forwards)"
    lines = []
    for f_ in forwards:
        parts = [f_.get("name", "?")]
        parts.append("enabled" if f_.get("enabled") else "DISABLED")
        dst = f_.get("dst_port", "")
        fwd = f_.get("fwd", "")
        fwd_port = f_.get("fwd_port", "")
        proto = f_.get("proto", "")
        if dst and fwd:
            parts.append(f"{proto}:{dst} → {fwd}:{fwd_port}")
        parts.append(f"id={f_.get('id', '?')}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_dpi(dpi: dict[str, Any]) -> str:
    """Format DPI restrictions."""
    groups = dpi.get("groups", [])
    apps = dpi.get("apps", [])
    if not groups and not apps:
        return "(no DPI restrictions configured)"

    lines = []
    if groups:
        lines.append(f"## Groups ({len(groups)})")
        for g in groups:
            status = "enabled" if g.get("enabled") else "DISABLED"
            lines.append(f"{g.get('name', '?')} | {status} | id={g.get('id', '?')}")
    if apps:
        lines.append(f"\n## Apps ({len(apps)})")
        for a in apps[:30]:  # Cap for token efficiency
            status = "enabled" if a.get("enabled") else "DISABLED"
            lines.append(f"{a.get('name', '?')} | {status} | group={a.get('group_id', '?')}")
        if len(apps) > 30:
            lines.append(f"... ({len(apps) - 30} more)")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Sites
# ------------------------------------------------------------------


def format_sites(sites: list[dict[str, Any]]) -> str:
    """Format sites as compact lines."""
    if not sites:
        return "(no sites)"
    lines = []
    for s in sites:
        parts = [s.get("name", "?")]
        desc = s.get("description", "")
        if desc:
            parts.append(desc)
        parts.append(f"id={s.get('id', '?')}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)
