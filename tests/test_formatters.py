"""Tests for output formatters."""

from __future__ import annotations

from typing import Any

from ubiquiti_unifi_blade_mcp.formatters import (
    format_client_detail,
    format_client_line,
    format_client_list,
    format_device_detail,
    format_device_line,
    format_device_list,
    format_dpi,
    format_firewall_policies,
    format_info,
    format_network_detail,
    format_network_list,
    format_port_forwards,
    format_resource_detail,
    format_resource_list,
    format_sites,
    format_traffic_routes,
    format_traffic_rules,
    format_wlan_list,
)


class TestDeviceFormatters:
    def test_device_line_ap(self, sample_devices: list[dict[str, Any]]) -> None:
        line = format_device_line(sample_devices[0])
        assert "Office AP" in line
        assert "uap" in line
        assert "U6-Pro" in line
        assert "connected" in line
        assert "clients=12" in line
        assert "aa:bb:cc:dd:ee:01" in line

    def test_device_line_upgrade_available(self, sample_devices: list[dict[str, Any]]) -> None:
        line = format_device_line(sample_devices[1])
        assert "UPGRADE_AVAILABLE" in line

    def test_device_list_empty(self) -> None:
        assert format_device_list([]) == "(no devices)"

    def test_device_list(self, sample_devices: list[dict[str, Any]]) -> None:
        result = format_device_list(sample_devices)
        lines = result.strip().split("\n")
        assert len(lines) == 3

    def test_device_detail(self, sample_devices: list[dict[str, Any]]) -> None:
        dev = {**sample_devices[0], "model_name": "UniFi 6 Pro", "last_seen": 1234567890, "ports": []}
        result = format_device_detail(dev)
        assert "Office AP" in result
        assert "U6-Pro" in result
        assert "UniFi 6 Pro" in result
        assert "7.1.68" in result

    def test_device_detail_with_ports(self) -> None:
        dev = {
            "name": "Switch",
            "mac": "aa:bb:cc:00:00:01",
            "model": "USW-24",
            "model_name": "",
            "type": "usw",
            "ip": "192.168.1.2",
            "version": "7.1.26",
            "state": 1,
            "adopted": True,
            "uptime": 86400,
            "clients": 5,
            "upgradeable": False,
            "last_seen": 0,
            "ports": [
                {"port_idx": 1, "name": "Port 1", "up": True, "speed": 1000, "poe_enable": True, "poe_power": "12.5"},
                {"port_idx": 2, "name": "Port 2", "up": False, "speed": 0, "poe_enable": False, "poe_power": ""},
            ],
        }
        result = format_device_detail(dev)
        assert "Ports (2)" in result
        assert "1000Mbps" in result
        assert "PoE=12.5W" in result
        assert "down" in result

    def test_uptime_formatting(self, sample_devices: list[dict[str, Any]]) -> None:
        # 864000s = 10d
        line = format_device_line(sample_devices[0])
        assert "up=10d0h" in line

        # 2592000s = 30d
        line = format_device_line(sample_devices[1])
        assert "up=30d0h" in line


class TestClientFormatters:
    def test_client_line_wireless(self, sample_clients: list[dict[str, Any]]) -> None:
        line = format_client_line(sample_clients[0])
        assert "MacBook Pro" in line
        assert "ip=192.168.1.100" in line
        assert "ssid=HomeNet" in line
        assert "rssi=-55" in line
        assert "exp=98%" in line

    def test_client_line_wired(self, sample_clients: list[dict[str, Any]]) -> None:
        line = format_client_line(sample_clients[1])
        assert "NAS" in line
        assert "wired" in line
        assert "ssid=" not in line

    def test_client_line_blocked(self, sample_clients: list[dict[str, Any]]) -> None:
        line = format_client_line(sample_clients[2])
        assert "BLOCKED" in line

    def test_client_list_empty(self) -> None:
        assert format_client_list([]) == "(no clients)"

    def test_client_list(self, sample_clients: list[dict[str, Any]]) -> None:
        result = format_client_list(sample_clients)
        lines = result.strip().split("\n")
        assert len(lines) == 3

    def test_client_detail(self) -> None:
        client = {
            "name": "MacBook",
            "hostname": "macbook.local",
            "mac": "11:22:33:44:55:01",
            "ip": "192.168.1.100",
            "network": "LAN",
            "essid": "HomeNet",
            "is_wired": False,
            "signal": -55,
            "experience": 98,
            "blocked": False,
            "uptime": 43200,
            "tx_bytes": 1073741824,
            "rx_bytes": 5368709120,
            "oui": "Apple",
            "ap_mac": "aa:bb:cc:dd:ee:01",
        }
        result = format_client_detail(client)
        assert "MacBook" in result
        assert "macbook.local" in result
        assert "HomeNet" in result
        assert "-55 dBm" in result
        assert "Apple" in result
        assert "1.0GB" in result
        assert "5.0GB" in result


class TestWlanFormatters:
    def test_wlan_list(self, sample_wlans: list[dict[str, Any]]) -> None:
        result = format_wlan_list(sample_wlans)
        assert "HomeNet" in result
        assert "enabled" in result
        assert "DISABLED" in result
        assert "guest" in result

    def test_wlan_list_empty(self) -> None:
        assert format_wlan_list([]) == "(no WLANs)"


class TestNetworkFormatters:
    def test_network_list(self, sample_networks: list[dict[str, Any]]) -> None:
        result = format_network_list(sample_networks)
        assert "Management" in result
        assert "vlan=1" in result
        assert "DISABLED" in result  # Guest is disabled
        assert "subnet=10.1.1.254/24" in result
        assert "id=n1" in result

    def test_network_list_empty(self) -> None:
        assert format_network_list([]) == "(no networks)"

    def test_network_detail(self, sample_networks: list[dict[str, Any]]) -> None:
        result = format_network_detail(sample_networks[0])
        assert "Name: Management" in result
        assert "VLAN: 1" in result
        assert "Subnet: 10.1.1.254/24" in result
        assert "Gateway: 10.1.1.254" in result
        assert "ID: n1" in result

    def test_network_detail_vlan_zero(self) -> None:
        result = format_network_detail({"id": "n0", "name": "Default", "vlan": 0, "enabled": True})
        assert "VLAN: 0" in result


class TestResourceFormatters:
    def test_resource_list(self) -> None:
        items = [
            {"id": "p1", "name": "Block IoT→LAN", "action": "BLOCK", "enabled": True},
            {"id": "p2", "name": "Allow DNS", "action": "ALLOW", "enabled": False},
        ]
        result = format_resource_list(items, "firewall_policies")
        assert "Block IoT→LAN" in result
        assert "action=BLOCK" in result
        assert "DISABLED" in result
        assert "id=p1" in result

    def test_resource_list_empty(self) -> None:
        assert format_resource_list([], "vouchers") == "(no vouchers)"

    def test_resource_list_label_fallback(self) -> None:
        # No name/ssid/domain → falls back to id as the label, not duplicated.
        result = format_resource_list([{"id": "x1", "type": "IPV4"}], "acl_rules")
        assert result == "x1 | type=IPV4"

    def test_resource_detail(self) -> None:
        item = {"id": "p1", "name": "P", "source": {"zoneId": "z1"}, "enabled": True}
        result = format_resource_detail(item)
        assert "id: p1" in result
        assert "name: P" in result
        assert '"zoneId":"z1"' in result  # nested rendered as compact JSON

    def test_resource_detail_not_found(self) -> None:
        assert format_resource_detail(None) == "(not found)"


class TestFirewallFormatters:
    def test_firewall_policies(self) -> None:
        policies = [
            {"id": "p1", "name": "Block IoT → LAN", "enabled": True, "action": "drop"},
            {"id": "p2", "name": "Allow DNS", "enabled": True, "action": "accept"},
        ]
        result = format_firewall_policies(policies)
        assert "Block IoT → LAN" in result
        assert "action=drop" in result

    def test_firewall_policies_empty(self) -> None:
        assert format_firewall_policies([]) == "(no firewall policies)"

    def test_traffic_routes(self) -> None:
        routes = [{"id": "r1", "description": "VPN split tunnel", "enabled": True, "matching_target": "domain"}]
        result = format_traffic_routes(routes)
        assert "VPN split tunnel" in result
        assert "enabled" in result

    def test_traffic_routes_empty(self) -> None:
        assert format_traffic_routes([]) == "(no traffic routes)"

    def test_traffic_rules_empty(self) -> None:
        assert format_traffic_rules([]) == "(no traffic rules)"

    def test_port_forwards(self) -> None:
        fwds = [
            {
                "id": "f1",
                "name": "SSH",
                "enabled": True,
                "dst_port": "2222",
                "fwd_port": "22",
                "fwd": "192.168.1.50",
                "proto": "tcp",
            }
        ]
        result = format_port_forwards(fwds)
        assert "SSH" in result
        assert "tcp:2222 → 192.168.1.50:22" in result

    def test_port_forwards_empty(self) -> None:
        assert format_port_forwards([]) == "(no port forwards)"


class TestDpiFormatters:
    def test_dpi_empty(self) -> None:
        assert format_dpi({"groups": [], "apps": []}) == "(no DPI restrictions configured)"

    def test_dpi_with_data(self) -> None:
        dpi = {
            "groups": [{"id": "g1", "name": "Social Media", "enabled": True}],
            "apps": [{"id": "a1", "name": "TikTok", "enabled": True, "group_id": "g1"}],
        }
        result = format_dpi(dpi)
        assert "Social Media" in result
        assert "TikTok" in result


class TestInfoFormatter:
    def test_info_connected(self) -> None:
        info = {
            "controllers": [
                {
                    "controller": "default",
                    "host": "192.168.1.1",
                    "status": "connected",
                    "version": "4.0.21",
                    "hostname": "UDM-Pro",
                    "site": "default",
                    "devices": 5,
                    "clients": 30,
                }
            ],
            "total_devices": 5,
            "total_clients": 30,
            "write_enabled": False,
        }
        result = format_info(info)
        assert "connected" in result
        assert "v4.0.21" in result
        assert "devices=5" in result
        assert "clients=30" in result
        assert "Write enabled: False" in result

    def test_info_error(self) -> None:
        info = {
            "controllers": [{"controller": "home", "status": "error", "error": "Connection refused"}],
            "total_devices": 0,
            "total_clients": 0,
            "write_enabled": False,
        }
        result = format_info(info)
        assert "error" in result
        assert "Connection refused" in result


class TestSitesFormatter:
    def test_sites(self) -> None:
        sites = [
            {"id": "default", "name": "Default", "description": "Main site"},
            {"id": "remote", "name": "Remote Office", "description": ""},
        ]
        result = format_sites(sites)
        assert "Default" in result
        assert "Main site" in result
        assert "Remote Office" in result

    def test_sites_empty(self) -> None:
        assert format_sites([]) == "(no sites)"
