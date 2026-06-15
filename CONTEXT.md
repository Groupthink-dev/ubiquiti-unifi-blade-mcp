# ubiquiti-unifi-blade-mcp Domain Context

## Terminology

- **DHCP Reservation**: A fixed-IP assignment stored on a UniFi client/user row. This is configuration evidence, not proof the device is currently online. The evidence tool reads `/api/s/{site}/rest/user`, includes only fixed-IP rows, and filters disabled or incomplete rows.
- **Connected Client**: A live client association from the UniFi clients handler. Use `unifi_clients` or `unifi_client` for liveness, signal, experience, and blocked status.
- **Local DNS Record**: A record-shaped `dns_policies` Integration API row with a record name, record type, and value. Policy-only DNS rows are not Local DNS Records and should not be rendered by `unifi_dns_records`.
- **Record Value**: The target value for a Local DNS Record, such as an IPv4 address for `A` or canonical hostname for `CNAME`. The UniFi API has used several field names for this value, so client normalization accepts `value`, `target`, `ipAddress`, and `canonicalName` variants.

## Surface Boundary

The dedicated `unifi_dns_records` and `unifi_dhcp_reservations` tools are read-only evidence surfaces. The underlying `dns_policies` resource remains writable through generic `unifi_resource_create`, `unifi_resource_update`, and `unifi_resource_delete` when `UNIFI_WRITE_ENABLED=true` and `confirm=true` are supplied.
