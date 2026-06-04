# ubiquiti-unifi-blade-mcp

UniFi network monitoring, security, and network/VLAN management MCP. 23 tools, token-efficient output, multi-controller.

## Architecture

```
src/ubiquiti_unifi_blade_mcp/
├── server.py       — FastMCP 3.x server, 23 @mcp.tool decorators
├── client.py       — UniFiClient: aiounifi session auth + Integration API (X-API-KEY) layer, multi-controller, credential scrubbing
├── formatters.py   — Token-efficient output (pipe-delimited, null omission, human units)
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
- **Integration API layer** — network/VLAN tools use `_integration_request()` (a raw aiohttp call to `/proxy/network/integration/v1/...`), NOT aiounifi (which has no network handlers and can't inject the `X-API-KEY` header). Site IDs there are UUIDs → `_resolve_integration_site_id()` (cached).
- **networkconf is cookie-only** — the legacy private `/api/s/{site}/rest/networkconf` endpoint does NOT honor `X-API-KEY`; the Integration API `networks` resource is the X-API-KEY write path (Network 10.x).
- **Network payload schema** — `network_spec_from_args()` in `models.py` is the single adjustment point for the create payload; confirm exact routed/corporate-VLAN field names against the on-console schema (Phase 0) and update only there.
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
