# ubiquiti-unifi-blade-mcp

UniFi monitoring, security, and Integration-API resource management MCP. 29 tools, token-efficient output, multi-controller.

## Architecture

```
src/ubiquiti_unifi_blade_mcp/
├── server.py       — FastMCP 3.x server, 29 @mcp.tool decorators (incl. unifi_controllers discovery + _write_gate multi-console safety)
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

- **Two auth modes** — `ControllerConfig.auth_mode`: `session` (username/password → aiounifi, cookie/CSRF) drives the monitoring tools; `apikey` (`UNIFI_API_KEY` → `X-API-KEY`) drives the network/VLAN tools. A controller is valid with either; both may be set.
- **Integration API layer** — network/VLAN tools + generic resource tools use `_integration_request()` (a raw aiohttp call to `/proxy/network/integration/v1/...`), NOT aiounifi (which has no network handlers and can't inject the `X-API-KEY` header). Site IDs there are UUIDs → `_resolve_integration_site_id()` (cached). List responses are paginated `{offset,limit,count,totalCount,data:[]}`; GET-by-id returns the bare object.
- **Generic resource layer** — `integration_list/get/create/update/delete(resource, …)` + the `_INTEGRATION_RESOURCES` map (logical name → `(path, read_only)`) are the single place resource paths live. Exposed via 5 `unifi_resource_*` tools (resource enum `ResourceName` in server.py). Paths are source-verified (Art-of-WiFi v10 client): `wifi/broadcasts`, `firewall/policies`, `firewall/zones`, `acl-rules`, `dns/policies`, `hotspot/vouchers`, `traffic-matching-lists` — NOT the camelCase you'd guess. Add/correct a resource in ONE place (the map).
- **Not in the Integration API** — port forwards, traffic routes/rules, QoS, port profiles are absent from the official API; they stay on the legacy aiounifi read tools. Don't add them to `_INTEGRATION_RESOURCES`.
- **networkconf is cookie-only** — the legacy private `/api/s/{site}/rest/networkconf` endpoint does NOT honor `X-API-KEY`; the Integration API `networks` resource is the X-API-KEY write path (Network 10.x).
- **Network payload schema** — `network_spec_from_args()` in `models.py` is the single adjustment point for the create payload. The Integration API keys networks on a top-level `management` enum (NOT the legacy aiounifi `purpose` string): `UNMANAGED` (VLAN-only tag, body is just `{management,name,enabled,vlanId}`) vs `GATEWAY` (routed L3, adds nested `ipv4Configuration` = `{hostIpAddress,prefixLength,dhcpConfiguration:{mode:SERVER,ipAddressRange:{start,stop}}}`). VLAN ids cap at **4009**. Schema captured live on Network 10.x 2026-06-06; UNMANAGED create→delete verified live, GATEWAY create is best-effort (extra GATEWAY fields like `zoneId`/`internetAccessEnabled` are server-defaulted). The `purpose` tool arg maps to `management` via `_MANAGEMENT_BY_PURPOSE`.
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
