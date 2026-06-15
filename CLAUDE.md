# ubiquiti-unifi-blade-mcp

UniFi monitoring, security, and Integration-API resource management MCP. 32 tools, token-efficient output, multi-controller.

## Architecture

```
src/ubiquiti_unifi_blade_mcp/
├── server.py       — FastMCP 3.x server, 32 @mcp.tool decorators (incl. unifi_controllers discovery + _write_gate multi-console safety)
├── client.py       — UniFiClient: aiounifi session auth + Integration API (X-API-KEY) generic resource layer, multi-controller, credential scrubbing
├── formatters.py   — Token-efficient output (pipe-delimited, null omission, human units) + generic resource formatters
├── models.py       — ControllerConfig (auth_mode), write gate, parse_controllers(), network_spec_from_args()
└── auth.py         — BearerAuthMiddleware for HTTP transport
```

## Dev commands

```bash
make install-dev    # Install with dev + test deps
make test           # Unit tests (no controller needed)
make check          # ruff lint + format + mypy
make run            # Start MCP server (stdio)
```

## Key patterns

- **Two auth modes** — `ControllerConfig.auth_mode`: `session` (username/password → aiounifi, cookie/CSRF) drives monitoring tools plus DHCP Reservations; `apikey` (`UNIFI_API_KEY` → `X-API-KEY`) drives network/VLAN tools, Local DNS Records, and generic Integration API resources. A controller is valid with either; both may be set.
- **Integration API layer** — network/VLAN tools + `unifi_dns_records` + generic resource tools use `_integration_request()` (a raw aiohttp call to `/proxy/network/integration/v1/...`), NOT aiounifi (which has no network handlers and can't inject the `X-API-KEY` header). Site IDs there are UUIDs → `_resolve_integration_site_id()` (cached). List responses are paginated `{offset,limit,count,totalCount,data:[]}`; GET-by-id returns the bare object.
- **Generic resource layer** — `integration_list/get/create/update/delete(resource, …)` + the `_INTEGRATION_RESOURCES` map (logical name → `(path, read_only)`) are the single place resource paths live. Exposed via 5 `unifi_resource_*` tools (resource enum `ResourceName` in server.py). Paths are source-verified (Art-of-WiFi v10 client): `networks`, `wifi/broadcasts`, `firewall/policies`, `firewall/zones`, `acl-rules`, `dns/policies`, `traffic-matching-lists`, `hotspot/vouchers`, `wans`, `radius/profiles`, `vpn/servers`, `vpn/site-to-site-tunnels`, `device-tags` — NOT the camelCase you'd guess. Add/correct a resource in ONE place (the map).
- **Local DNS Records** — `unifi_dns_records` is the dedicated read contract over Integration API `dns/policies`; it filters to record-shaped objects and emits `name | TYPE | value=... | ttl=... | enabled`. `unifi_resource_list dns_policies` remains the generic/raw-ish debug path and also surfaces `value=`.
- **DHCP Reservations** — `unifi_dhcp_reservations` is session-auth only and reads legacy `/api/s/{site}/rest/user` via `ctrl.request(ApiRequest("get", path, None))`; include only active reservation intent (`use_fixedip` truthy + `fixed_ip` + `mac`), including offline clients. Do NOT use `ctrl.clients` for reservations; connected clients are active-only and are a different evidence class.
- **Evidence language** — Connected Client = currently active on the network; DHCP Reservation = UniFi intends to assign an IP to a MAC; Local DNS Record = UniFi intends local name resolution. Do not overclaim liveness or public-DNS intent from these tools.
- **Not in the Integration API** — port forwards, traffic routes/rules, QoS, port profiles are absent from the official API; they stay on the legacy aiounifi read tools. Don't add them to `_INTEGRATION_RESOURCES`.
- **networkconf is cookie-only** — the legacy private `/api/s/{site}/rest/networkconf` endpoint does NOT honor `X-API-KEY`; the Integration API `networks` resource is the X-API-KEY write path (Network 10.x).
- **Network payload schema** — `network_spec_from_args()` in `models.py` is the single adjustment point for the create payload. The Integration API keys networks on a top-level `management` enum (NOT the legacy aiounifi `purpose` string): `UNMANAGED` (VLAN-only tag, body is just `{management,name,enabled,vlanId}`) vs `GATEWAY` (routed L3, adds nested `ipv4Configuration` = `{hostIpAddress,prefixLength,dhcpConfiguration:{mode:SERVER,ipAddressRange:{start,stop}}}`). VLAN ids cap at **4009**. GATEWAY also requires non-null scalars (`isolationEnabled`/`cellularBackupEnabled`/`internetAccessEnabled` + `ipv4Configuration.autoScaleEnabled`; with DHCP, `leaseTimeSeconds`+`pingConflictDetectionEnabled`) — the API rejects null, so the builder applies conservative defaults. Schema captured live on Network 10.x 2026-06-06; **both UNMANAGED and GATEWAY create→delete verified live** on paddington. The `purpose` tool arg maps to `management` via `_MANAGEMENT_BY_PURPOSE`.
- **aiounifi is async** — no `asyncio.to_thread` needed, unlike sync-wrapped MCPs
- **Multi-controller** — `UNIFI_CONTROLLERS=home,office` + per-controller env vars (incl. `UNIFI_{NAME}_API_KEY`)
- **Write gate** — `UNIFI_WRITE_ENABLED=true` required for mutations, destructive ops also need `confirm=true`
- **HTTP transport** — stdio is the default (and the only harness-launched mode). When `UNIFI_MCP_TRANSPORT=http`, `main()` refuses to start without `UNIFI_MCP_API_TOKEN` (loopback-only, never unauthenticated).
- **Credential scrubbing** — regex patterns strip passwords, cookies, CSRF/`X-API-KEY`/bearer tokens from errors
- **Handler objects** — aiounifi enable/disable methods take model objects, not string IDs; fetch the object first via `.get(id)`
- **DPI handlers** — `ctrl.dpi_groups` and `ctrl.dpi_apps` (not `ctrl.dpi_restriction_*`)
- **ApiRequest** — `ctrl.request()` takes `ApiRequest(method, path, data)`, not positional args
- **No `len()` on handlers** — aiounifi handlers don't implement `__len__`; use `sum(1 for _ in handler.values())`

## Testing

Tests are fully mocked — no UniFi controller required. Fixtures in `tests/conftest.py`.

## Dependencies

- `aiounifi>=90` — requires Python >=3.13
- `fastmcp>=2.0.0` — MCP framework (currently using 3.x)
- `aiohttp` — async HTTP for aiounifi sessions
