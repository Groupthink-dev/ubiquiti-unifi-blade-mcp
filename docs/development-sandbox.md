# UniFi Development Sandbox

This repo now has a disposable UniFi Network application target for live
development and write-path verification.

## Endpoint

| Field | Value |
|---|---|
| Fixture | `sb-vm-unifi-01` |
| Appliance | UniFi OS Server |
| Application under test | UniFi Network |
| Controller URL | `https://10.1.70.14:11443` |
| Local hostname | `unifi-test.gen3.dev` only where the static hostname from `unifi.paddington.cc` is available |
| TrueNAS host | `tn-sb` |
| Baseline snapshot | `data-sb/vm/sb-vm-unifi-01-root@unifi-blade-baseline` |
| Credential item | `1p/infra/unifi-test` |

Use this target for live checks that need a disposable UniFi Network controller,
especially Integration API writes. Keep production controllers for observational
read parity only. The default baseline is now post-UniFi setup: the UniFi
Network application is configured, sandbox credentials/API key are captured in
1Password, and the baseline snapshot has been refreshed.

Example single-controller environment:

```bash
export UNIFI_HOST="10.1.70.14"
export UNIFI_PORT="11443"
export UNIFI_VERIFY_SSL="false"
export UNIFI_USERNAME="<sandbox-local-admin>"
export UNIFI_PASSWORD="<sandbox-password>"
export UNIFI_API_KEY="<sandbox-integration-api-key>"
```

For mutating suites, still require the normal write gates:

```bash
export UNIFI_WRITE_ENABLED="true"
```

## Reset Workflow

Snapshot and restore are owned by Starbase, not this blade. The blade consumes a
controller endpoint; it must not grow TrueNAS VM lifecycle logic.

From the Starbase repo:

```bash
cd /Users/piers/src/starbase
scripts/truenas-unifi-fixture.py status
scripts/truenas-unifi-fixture.py fresh --apply --wait-ready
```

Useful Starbase commands:

```bash
scripts/truenas-unifi-fixture.py capture-baseline --apply
scripts/truenas-unifi-fixture.py fresh --baseline unifi-blade-baseline --apply --wait-ready
scripts/truenas-unifi-fixture.py delete-snapshot --snapshot <snapshot-name> --apply
```

The default mode is dry-run; `--apply` is required for VM stop/start, snapshot,
rollback, and deletion.

The VM also has an additional unconfigured network interface available for
future network-topology tests. Leave it unused unless the test plan explicitly
requires multi-homing.

## Build Provenance

The VM is an Ubuntu 24.04 Noble full VM provisioned with cloud-init, then
converted into a UniFi OS Server appliance. It was not built as LXC, jail, or the
legacy self-hosted Network Application container; those paths do not provide the
same UniFi OS Server surface and Integration API behavior.

Primary Starbase references:

- `/Users/piers/src/starbase/docs/runbooks/unifi-os-server-vm.md`
- `/Users/piers/src/starbase/scripts/truenas-unifi-fixture.py`
- `/Users/piers/src/starbase/truenas/vms.nix`

Installer provenance:

- Official installer source: `https://help.ui.com/hc/en-us/articles/34210126298775-Self-Hosting-UniFi`
- Community install-script discussion: `https://community.ui.com/questions/UniFi-OS-Server-Installation-Scripts-or-UniFi-Network-Application-Installation-Scripts-or-UniFi-Eas/ccbc7530-dd61-40a7-82ec-22b17f027776`

## Test Discipline

- Unit tests remain fully mocked and must not require the sandbox.
- Live tests may use the sandbox endpoint and reset it with the Starbase fixture
  script before destructive or stateful suites.
- Do not point mutating development runs at production controllers.
- Preserve evidence language: DHCP Reservations are intended address assignment,
  connected clients are live presence, and Local DNS Records are local resolver
  intent.
