"""Server-layer tests — the multi-console write gate and discovery tool.

These exercise the DD-343 connection-scoping safety rule: a mutating tool with
an omitted ``controller`` is refused when more than one console is configured,
so a write can never silently land on the default (first) console.
"""

from __future__ import annotations

import pytest

from ubiquiti_unifi_blade_mcp import server


@pytest.fixture(autouse=True)
def _reset_client_singleton() -> None:
    """Force each test to rebuild the lazy client from its own env."""
    server._client = None
    yield
    server._client = None


class TestWriteGate:
    def test_writes_disabled_blocks_regardless_of_controller(self, mock_env: None) -> None:
        # mock_env does not set UNIFI_WRITE_ENABLED.
        assert "disabled" in (server._write_gate("default") or "")

    def test_single_console_omit_allowed(self, mock_env_write: None) -> None:
        assert server._write_gate(None) is None

    def test_multi_console_omit_refused(self, mock_env_multi: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNIFI_WRITE_ENABLED", "true")
        gate = server._write_gate(None)
        assert gate is not None
        assert "2 controllers configured" in gate
        assert "home" in gate and "office" in gate

    def test_multi_console_explicit_allowed(self, mock_env_multi: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNIFI_WRITE_ENABLED", "true")
        assert server._write_gate("office") is None


class TestControllersTool:
    @pytest.mark.asyncio
    async def test_lists_single_with_default_marker(self, mock_env: None) -> None:
        out = await server.unifi_controllers()
        assert "default (default) — 192.168.1.1" in out

    @pytest.mark.asyncio
    async def test_lists_multi_with_selection_hint(self, mock_env_multi: None) -> None:
        out = await server.unifi_controllers()
        assert "home (default) — 192.168.1.1" in out
        assert "office — 10.0.0.1" in out
        assert "mutations require it" in out
