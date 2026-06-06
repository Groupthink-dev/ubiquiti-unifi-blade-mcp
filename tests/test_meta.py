"""CONV-29 ``_meta`` audit-tail envelope tests.

Every successful tool return carries the canonical ``_meta: {...}`` JSON tail
appended after a blank line; error/gate/sentinel returns stay plain. These tests
exercise one representative read tool, one write tool, and one error path through
the server layer (the client is mocked, no controller required).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from ubiquiti_unifi_blade_mcp import server


@pytest.fixture(autouse=True)
def _reset_client_singleton() -> None:
    """Force each test to rebuild the lazy client from its own env."""
    server._client = None
    yield
    server._client = None


def _split_meta(out: str) -> tuple[str, dict[str, Any]]:
    """Split a tool output into (payload, parsed_meta_json)."""
    marker = "\n\n_meta: "
    assert marker in out, f"expected a _meta tail, got: {out!r}"
    payload, _, tail = out.partition(marker)
    meta = json.loads(tail)
    return payload, meta


class FakeClient:
    """Stand-in for UniFiClient with just the methods the tested tools call."""

    def __init__(self) -> None:
        self.controller_names = ["default"]

    async def get_networks(self, controller: str | None) -> list[dict[str, Any]]:
        return [
            {"id": "n1", "name": "LAN", "vlan": 1, "enabled": True},
            {"id": "n2", "name": "Guest", "vlan": 30, "enabled": False},
        ]

    async def unblock_client(self, mac: str, controller: str | None) -> None:
        return None


class TestMetaTail:
    @pytest.mark.asyncio
    async def test_read_tool_carries_meta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A list/read tool appends a valid _meta tail with the expected count."""
        monkeypatch.setattr(server, "_get_client", lambda: FakeClient())
        out = await server.unifi_networks()
        payload, meta = _split_meta(out)
        # The formatted payload is preserved verbatim before the tail.
        assert "LAN" in payload and "Guest" in payload
        assert meta["matched_total"] == 2
        assert meta["returned"] == 2
        assert "latency_ms" in meta and isinstance(meta["latency_ms"], int)

    @pytest.mark.asyncio
    async def test_write_tool_carries_meta(self, mock_env_write: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """A write tool (write enabled) appends a _meta tail with count 1."""
        monkeypatch.setattr(server, "_get_client", lambda: FakeClient())
        out = await server.unifi_unblock_client("11:22:33:44:55:66")
        payload, meta = _split_meta(out)
        assert "Unblocked client 11:22:33:44:55:66" in payload
        assert meta["matched_total"] == 1
        assert meta["returned"] == 1
        assert "latency_ms" in meta

    @pytest.mark.asyncio
    async def test_gate_path_has_no_meta(self, mock_env: None) -> None:
        """A write tool with writes disabled returns a plain gate string (no _meta)."""
        # mock_env does not set UNIFI_WRITE_ENABLED → require_write gate fires.
        out = await server.unifi_unblock_client("11:22:33:44:55:66")
        assert "_meta:" not in out
        assert "disabled" in out
