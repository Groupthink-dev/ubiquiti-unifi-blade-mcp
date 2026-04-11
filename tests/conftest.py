"""Shared fixtures for ubiquiti-unifi-blade-mcp tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture()
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set minimal UniFi environment variables."""
    monkeypatch.setenv("UNIFI_HOST", "192.168.1.1")
    monkeypatch.setenv("UNIFI_USERNAME", "admin")
    monkeypatch.setenv("UNIFI_PASSWORD", "test-password")


@pytest.fixture()
def mock_env_multi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set multi-controller environment variables."""
    monkeypatch.setenv("UNIFI_CONTROLLERS", "home,office")
    monkeypatch.setenv("UNIFI_HOME_HOST", "192.168.1.1")
    monkeypatch.setenv("UNIFI_HOME_USERNAME", "admin")
    monkeypatch.setenv("UNIFI_HOME_PASSWORD", "home-password")
    monkeypatch.setenv("UNIFI_OFFICE_HOST", "10.0.0.1")
    monkeypatch.setenv("UNIFI_OFFICE_USERNAME", "admin")
    monkeypatch.setenv("UNIFI_OFFICE_PASSWORD", "office-password")


@pytest.fixture()
def mock_env_write(monkeypatch: pytest.MonkeyPatch, mock_env: None) -> None:
    """Enable write operations."""
    monkeypatch.setenv("UNIFI_WRITE_ENABLED", "true")


@pytest.fixture()
def sample_devices() -> list[dict[str, Any]]:
    """Sample device list."""
    return [
        {
            "mac": "aa:bb:cc:dd:ee:01",
            "name": "Office AP",
            "model": "U6-Pro",
            "type": "uap",
            "ip": "192.168.1.10",
            "version": "7.1.68",
            "state": 1,
            "adopted": True,
            "uptime": 864000,
            "clients": 12,
            "upgradeable": False,
        },
        {
            "mac": "aa:bb:cc:dd:ee:02",
            "name": "Core Switch",
            "model": "USW-Pro-48-PoE",
            "type": "usw",
            "ip": "192.168.1.2",
            "version": "7.1.26",
            "state": 1,
            "adopted": True,
            "uptime": 2592000,
            "clients": 0,
            "upgradeable": True,
        },
        {
            "mac": "aa:bb:cc:dd:ee:03",
            "name": "Gateway",
            "model": "UDM-Pro",
            "type": "ugw",
            "ip": "192.168.1.1",
            "version": "4.0.21",
            "state": 1,
            "adopted": True,
            "uptime": 5184000,
            "clients": 0,
            "upgradeable": False,
        },
    ]


@pytest.fixture()
def sample_clients() -> list[dict[str, Any]]:
    """Sample client list."""
    return [
        {
            "mac": "11:22:33:44:55:01",
            "name": "MacBook Pro",
            "ip": "192.168.1.100",
            "network": "LAN",
            "essid": "HomeNet",
            "is_wired": False,
            "signal": -55,
            "experience": 98,
            "blocked": False,
            "uptime": 43200,
        },
        {
            "mac": "11:22:33:44:55:02",
            "name": "NAS",
            "ip": "192.168.1.50",
            "network": "LAN",
            "essid": "",
            "is_wired": True,
            "signal": None,
            "experience": 100,
            "blocked": False,
            "uptime": 2592000,
        },
        {
            "mac": "11:22:33:44:55:03",
            "name": "Unknown Device",
            "ip": "192.168.1.200",
            "network": "IoT",
            "essid": "IoT-Net",
            "is_wired": False,
            "signal": -72,
            "experience": 65,
            "blocked": True,
            "uptime": 3600,
        },
    ]


@pytest.fixture()
def sample_wlans() -> list[dict[str, Any]]:
    """Sample WLAN list."""
    return [
        {"id": "wlan001", "name": "HomeNet", "enabled": True, "security": "wpa2", "is_guest": False},
        {"id": "wlan002", "name": "IoT-Net", "enabled": True, "security": "wpa2", "is_guest": False},
        {"id": "wlan003", "name": "Guest", "enabled": False, "security": "wpa2", "is_guest": True},
    ]
