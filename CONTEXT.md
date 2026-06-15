# UniFi Blade MCP

This context defines the network-domain language used by the UniFi MCP tools and their downstream consumers.

## Language

**DHCP Reservation**:
A UniFi-managed address assignment that reserves a specific IP address for a client MAC address through DHCP, whether or not the client is currently connected. It is evidence of intended address assignment, not evidence that the host is currently alive.
_Avoid_: fixed IP, static DHCP, reserved device

**Connected Client**:
A client device currently visible to UniFi as active on the network, with live connection details such as IP address, SSID or wired association, signal, and experience score. It is evidence of current activity, not evidence that the address is reserved.
_Avoid_: DHCP reservation, reserved client

**Local DNS Record**:
An explicit UniFi-managed DNS record, such as an A, AAAA, or CNAME record, used for local name resolution. It is evidence of local resolver intent, not evidence that public DNS should mirror it.
_Avoid_: DNS policy, static-DNS record, local-DNS override

**Record Value**:
The normalized target data of a Local DNS Record, such as an IP address for an A or AAAA record or a canonical name for a CNAME record.
_Avoid_: content, data, rdata
