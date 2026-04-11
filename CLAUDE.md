# ubiquiti-unifi-blade-mcp

UniFi network monitoring and security MCP. 18 tools, token-efficient output, multi-controller.

## Architecture

```
src/ubiquiti_unifi_blade_mcp/
├── server.py       — FastMCP 3.x server, 18 @mcp.tool decorators
├── client.py       — UniFiClient wrapping aiounifi, multi-controller, credential scrubbing
├── formatters.py   — Token-efficient output (pipe-delimited, null omission, human units)
├── models.py       — ControllerConfig, write gate, parse_controllers()
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

- **aiounifi is async** — no `asyncio.to_thread` needed, unlike sync-wrapped MCPs
- **Multi-controller** — `UNIFI_CONTROLLERS=home,office` + per-controller env vars
- **Write gate** — `UNIFI_WRITE_ENABLED=true` required for mutations, destructive ops also need `confirm=true`
- **Credential scrubbing** — 6 regex patterns strip passwords, cookies, tokens from errors
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
