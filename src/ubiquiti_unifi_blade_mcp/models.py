"""Shared constants, types, and gates for Ubiquiti UniFi Blade MCP server."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Default limits for list operations (token efficiency)
DEFAULT_CLIENT_LIMIT = 50
DEFAULT_DEVICE_LIMIT = 30
DEFAULT_EVENT_LIMIT = 20


@dataclass
class ControllerConfig:
    """Configuration for a single UniFi controller."""

    name: str
    host: str
    username: str
    password: str
    port: int = 443
    site: str = "default"
    verify_ssl: bool = False
    totp_secret: str = ""


def parse_controllers() -> list[ControllerConfig]:
    """Parse UniFi controller configuration from environment variables.

    Supports two modes:

    1. Multi-controller: ``UNIFI_CONTROLLERS=home,office`` with per-controller
       ``UNIFI_HOME_HOST``, ``UNIFI_HOME_USERNAME``, ``UNIFI_HOME_PASSWORD``

    2. Single-controller (default): ``UNIFI_HOST``, ``UNIFI_USERNAME``,
       ``UNIFI_PASSWORD`` treated as controller "default".
    """
    controllers_str = os.environ.get("UNIFI_CONTROLLERS", "").strip()
    if controllers_str:
        controllers = []
        for name in controllers_str.split(","):
            name = name.strip()
            prefix = f"UNIFI_{name.upper()}_"
            host = os.environ.get(f"{prefix}HOST", "")
            username = os.environ.get(f"{prefix}USERNAME", "")
            password = os.environ.get(f"{prefix}PASSWORD", "")
            if not all([host, username, password]):
                logger.warning("Incomplete config for controller %s — skipping", name)
                continue
            controllers.append(
                ControllerConfig(
                    name=name,
                    host=host,
                    username=username,
                    password=password,
                    port=int(os.environ.get(f"{prefix}PORT", "443")),
                    site=os.environ.get(f"{prefix}SITE", "default"),
                    verify_ssl=os.environ.get(f"{prefix}VERIFY_SSL", "false").lower() == "true",
                    totp_secret=os.environ.get(f"{prefix}TOTP_SECRET", ""),
                )
            )
        if not controllers:
            raise ValueError("UNIFI_CONTROLLERS set but no controllers configured correctly")
        return controllers

    # Single-controller mode
    host = os.environ.get("UNIFI_HOST", "")
    username = os.environ.get("UNIFI_USERNAME", "")
    password = os.environ.get("UNIFI_PASSWORD", "")
    if not all([host, username, password]):
        raise ValueError("UniFi credentials not configured. Set UNIFI_HOST, UNIFI_USERNAME, UNIFI_PASSWORD")
    return [
        ControllerConfig(
            name="default",
            host=host,
            username=username,
            password=password,
            port=int(os.environ.get("UNIFI_PORT", "443")),
            site=os.environ.get("UNIFI_SITE", "default"),
            verify_ssl=os.environ.get("UNIFI_VERIFY_SSL", "false").lower() == "true",
            totp_secret=os.environ.get("UNIFI_TOTP_SECRET", ""),
        )
    ]


def is_write_enabled() -> bool:
    """Check if write operations are enabled via env var."""
    return os.environ.get("UNIFI_WRITE_ENABLED", "").lower() == "true"


def require_write() -> str | None:
    """Return an error message if writes are disabled, else None."""
    if not is_write_enabled():
        return "Error: Write operations are disabled. Set UNIFI_WRITE_ENABLED=true to enable."
    return None
