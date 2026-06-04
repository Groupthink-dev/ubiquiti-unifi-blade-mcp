# ubiquiti-unifi-blade-mcp

An MCP server that gives AI agents structured access to Ubiquiti UniFi network controllers. Built for the [Model Context Protocol](https://modelcontextprotocol.io) with security visibility and token efficiency as first-class design goals.

## Why this exists

UniFi controllers expose a rich but undocumented REST API behind cookie-based auth with CSRF tokens and optional 2FA. The [aiounifi](https://github.com/Kane610/aiounifi) library (MIT, powers the Home Assistant integration) handles the protocol complexity — UniFi OS vs classic controller detection, TOTP 2FA, websocket events. This MCP wraps it with the guardrails that automated agents need:

- **Security-first tool set** — 18 tools focused on what network security agents actually need: device health, client visibility, firewall state, traffic rules, DPI restrictions, port forwards. Not 161 tools for every possible configuration change.
- **Token-efficient output** — compact pipe-delimited format. A 30-device network in ~50 tokens per device. Client listings with signal strength, experience score, and blocked status at a glance.
- **Write-gated mutations** — client blocking, WLAN toggling, device restart, and traffic route changes require explicit opt-in via `UNIFI_WRITE_ENABLED=true`. Destructive operations (block, restart) additionally require per-call `confirm=true`.
- **Multi-controller** — manage home and office networks from a single MCP instance. Each controller authenticates independently with separate sessions.

## How this differs from other UniFi MCPs

| | ubiquiti-unifi-blade-mcp | sirkirby/unifi-mcp | enuno/unifi-mcp-server |
|---|---|---|---|
| **Focus** | Monitoring + security + network/VLAN mgmt (23 tools) | Full management (161 tools) | Full management (74 tools) |
| **Design for** | LLM agents (token-efficient) | Claude Code (lazy loading) | General MCP clients |
| **Multi-controller** | Native (env var config) | Single controller | Multi-mode (local/cloud) |
| **Write safety** | Dual-gated (env + confirm) | Preview-then-confirm | Permission model |
| **2FA support** | TOTP via aiounifi | TOTP support | API key option |
| **Output** | Pipe-delimited, compact | Full JSON | Full JSON |
| **Marketplace** | Sidereal certified | Claude Code plugin | Standalone |

Use this blade-MCP for agent-driven monitoring and security. Use sirkirby/unifi-mcp (available as a community listing in the Sidereal marketplace) when you need full network configuration management.

## Quick start

```bash
# Install
uv pip install -e .

# Configure (monitoring tools — username/password)
export UNIFI_HOST="192.168.1.1"
export UNIFI_USERNAME="admin"
export UNIFI_PASSWORD="your-password"
export UNIFI_VERIFY_SSL="false"  # Common for self-signed certs

# Configure (network/VLAN tools — Integration API key)
# Generate in UniFi Network → Settings → Control Plane → Integrations
export UNIFI_API_KEY="your-x-api-key"

# Run
ubiquiti-unifi-blade-mcp
```

## Authentication: two modes

| Mode | Env | Drives | Endpoint |
|------|-----|--------|----------|
| **Session** | `UNIFI_USERNAME` + `UNIFI_PASSWORD` (+ optional `UNIFI_TOTP_SECRET`) | Monitoring/security tools (devices, clients, firewall, WLANs, DPI, …) | Legacy controller API via `aiounifi` (cookie/CSRF) |
| **API key** | `UNIFI_API_KEY` (`X-API-KEY`) | Network/VLAN tools (`unifi_networks`, `unifi_create_network`, …) | Official **Integration API** (`/proxy/network/integration/v1`) — stateless |

Either or both may be set. The network/VLAN tools require the API key (the only path that supports VLAN writes); the monitoring tools require username/password. Generate the API key in UniFi Network → **Settings → Control Plane → Integrations**. Requires UniFi Network 9.0+ (network/VLAN CRUD confirmed on 10.x).

## 23 tools, 6 categories

### Info & Sites (2 tools)

| Tool | Purpose | Token cost |
|------|---------|------------|
| `unifi_info` | Health check — controller version, hostname, device/client counts, write gate | ~60 |
| `unifi_sites` | List sites on the controller | ~20/site |

### Networks & VLANs (2 read tools — require `UNIFI_API_KEY`)

| Tool | Purpose | Token cost |
|------|---------|------------|
| `unifi_networks` | List networks/VLANs — name, VLAN id, enabled, purpose, subnet | ~25/network |
| `unifi_network` | Full detail — VLAN id, subnet, gateway, purpose | ~60 |

### Devices (2 tools)

| Tool | Purpose | Token cost |
|------|---------|------------|
| `unifi_devices` | List APs, switches, gateways — model, state, clients, uptime, firmware | ~50/device |
| `unifi_device` | Full detail — port table with PoE, firmware, upgrade status | ~150 |

### Clients (2 tools)

| Tool | Purpose | Token cost |
|------|---------|------------|
| `unifi_clients` | Connected clients — name, IP, SSID, signal, experience, blocked | ~40/client |
| `unifi_client` | Full detail — TX/RX, vendor (OUI), AP association | ~120 |

### Firewall & Security (5 tools)

| Tool | Purpose | Token cost |
|------|---------|------------|
| `unifi_firewall` | Firewall policies — name, action, enabled/disabled | ~30/policy |
| `unifi_traffic_routes` | Traffic routes — description, enabled/disabled, target | ~25/route |
| `unifi_traffic_rules` | Traffic rules — description, action, enabled/disabled | ~25/rule |
| `unifi_port_forwards` | Port forwards — name, protocol, external → internal | ~30/fwd |
| `unifi_dpi` | DPI restriction groups and apps | ~20/item |

### Write Operations (10 tools, gated)

| Tool | Gate | Purpose |
|------|------|---------|
| `unifi_block_client` | write + confirm | Block a client from the network |
| `unifi_unblock_client` | write | Unblock a previously blocked client |
| `unifi_reconnect_client` | write | Force a wireless client to reconnect |
| `unifi_toggle_wlan` | write | Enable or disable an SSID |
| `unifi_toggle_traffic_route` | write | Enable or disable a traffic route |
| `unifi_restart_device` | write + confirm | Restart an AP, switch, or gateway |
| `unifi_create_network` | write + confirm + API key | Create a network/VLAN |
| `unifi_update_network` | write + confirm + API key | Update a network/VLAN (supplied fields) |
| `unifi_delete_network` | write + confirm + API key | Delete a network/VLAN |

### Output format

```
Office AP | uap | model=U6-Pro | ip=192.168.1.10 | connected | clients=12 | up=10d0h | mac=aa:bb:cc:dd:ee:01
Core Switch | usw | model=USW-Pro-48-PoE | ip=192.168.1.2 | connected | up=30d0h | UPGRADE_AVAILABLE | mac=aa:bb:cc:dd:ee:02
Gateway | ugw | model=UDM-Pro | ip=192.168.1.1 | connected | up=60d0h | mac=aa:bb:cc:dd:ee:03
```

```
MacBook Pro | ip=192.168.1.100 | ssid=HomeNet | rssi=-55 | exp=98% | up=12h0m | mac=11:22:33:44:55:01
NAS | ip=192.168.1.50 | wired | exp=100% | up=30d0h | mac=11:22:33:44:55:02
Unknown Device | ip=192.168.1.200 | ssid=IoT-Net | rssi=-72 | exp=65% | BLOCKED | mac=11:22:33:44:55:03
```

## Multi-controller support

```bash
export UNIFI_CONTROLLERS="home,office"
export UNIFI_HOME_HOST="192.168.1.1"
export UNIFI_HOME_USERNAME="admin"
export UNIFI_HOME_PASSWORD="home-password"
export UNIFI_OFFICE_HOST="10.0.0.1"
export UNIFI_OFFICE_USERNAME="admin"
export UNIFI_OFFICE_PASSWORD="office-password"
```

Pass `controller="office"` to any tool. Omit for the first configured controller.

## Security model

| Layer | Mechanism |
|-------|-----------|
| **Write gate** | `UNIFI_WRITE_ENABLED=true` required for any mutation |
| **Destructive confirm** | `unifi_block_client`, `unifi_restart_device`, and all `unifi_*_network` write tools require `confirm=true` |
| **Credential scrubbing** | Passwords, cookies, CSRF tokens, `X-API-KEY`, session IDs stripped from errors |
| **Controller API key** | `UNIFI_API_KEY` (`X-API-KEY`) — scoped Integration API key for network/VLAN tools |
| **HTTP transport auth** | `UNIFI_MCP_API_TOKEN` bearer token; HTTP transport **refuses to start** without it (loopback-only, stdio is the default) |
| **Session isolation** | Each controller authenticates independently |
| **SSL configurable** | `UNIFI_VERIFY_SSL=true` for environments with proper certs |
| **2FA support** | TOTP via `UNIFI_TOTP_SECRET` (base32 encoded) |

## Sidereal integration

```json
{
  "mcpServers": {
    "unifi": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "~/src/ubiquiti-unifi-blade-mcp", "run", "ubiquiti-unifi-blade-mcp"],
      "env": {
        "UNIFI_HOST": "192.168.1.1",
        "UNIFI_USERNAME": "admin",
        "UNIFI_PASSWORD": "...",
        "UNIFI_VERIFY_SSL": "false",
        "UNIFI_WRITE_ENABLED": "false"
      }
    }
  }
}
```

### Webhook trigger patterns

- **Device state changes** — `unifi_devices` returns state (connected/disconnected/upgrading), enabling alerts on AP/switch failures
- **New/unknown clients** — `unifi_clients` with blocked status for intrusion detection workflows
- **Firmware availability** — `unifi_devices` flags `UPGRADE_AVAILABLE` for maintenance scheduling
- **Firewall audit** — `unifi_firewall` + `unifi_port_forwards` for periodic security posture checks

## Development

```bash
make install-dev    # Install with dev + test dependencies
make test           # Unit tests (mocked, no controller needed)
make check          # Lint + format + type-check
make run            # Start MCP server (stdio)
```

### Architecture

```
src/ubiquiti_unifi_blade_mcp/
├── server.py       — FastMCP server, 23 @mcp.tool decorators
├── client.py       — UniFiClient: aiounifi session auth + Integration API (X-API-KEY) layer, multi-controller, credential scrubbing
├── formatters.py   — Token-efficient output (pipe-delimited, null omission, human units)
├── models.py       — Controller config, auth modes, write gate, network payload builder
└── auth.py         — Bearer token middleware for HTTP transport
```

Built with [FastMCP 2.0](https://github.com/jlowin/fastmcp) and [aiounifi](https://github.com/Kane610/aiounifi).

## Acknowledgements

- [Kane610/aiounifi](https://github.com/Kane610/aiounifi) — the async UniFi library that powers this and the Home Assistant integration
- [sirkirby/unifi-mcp](https://github.com/sirkirby/unifi-mcp) — comprehensive UniFi MCP for full network management (available as community listing)

## License

MIT
