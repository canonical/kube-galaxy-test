# Juju Unit Provider — Design & Implementation

## Overview

`JujuUnit` and `JujuUnitProvider` in `juju.py` allow kube-galaxy to provision
cluster nodes as **Juju machines** within the currently active Juju model.  All
standard `Unit` operations (`run`, `put`, `get`, `enlist`) are supported.

This document explains the provider's design, its differences from other providers
(LXD, Multipass, SSH), and the SSH reverse tunnel mechanism used to bridge Juju nodes
back to the orchestrator.

---

## Architecture

```
orchestrator machine
├── kube-galaxy CLI
├── ArtifactServer    (0.0.0.0:8765)
├── RegistryMirror    (0.0.0.0:5000)
│
└── SSH reverse tunnel process  ←──── per JujuUnit, started at enlist()
        juju ssh --no-host-key-checks <unit> \
            -N -R 8765:localhost:8765 \
               -R 5000:localhost:5000
                    │
                    ▼
        juju machine (remote cloud)
        ├── 127.0.0.1:8765  →  orchestrator ArtifactServer
        ├── 127.0.0.1:5000  →  orchestrator RegistryMirror
        └── /etc/hosts: kube-galaxy.orchestrator → 127.0.0.1
```

From the Juju machine's perspective, orchestrator services are on `localhost`.
This removes any requirement for the orchestrator's IP address to be routable from
within the cloud where Juju deploys its machines.

---

## Key Design Decisions

### Why a reverse tunnel instead of exposing the orchestrator's IP?

Other providers (LXD, Multipass) run nodes in a VM network that shares a bridge with
the orchestrator host, so `detect_ip()` returns a directly reachable address.
Juju can deploy machines on OpenStack, AWS, GCE, or any substrate — those machines may
have no path to the orchestrator's local IP.

A **reverse** tunnel is initiated *from* the orchestrator *to* the Juju machine via
SSH: only outbound port 22 is required from the orchestrator, which is almost always
available.  The tunnel then exposes the orchestrator's services on `127.0.0.1` from
the Juju machine's point of view.

### Why `127.0.0.1` in `/etc/hosts`?

SSH `-R port:localhost:port` binds the forwarded port on the *remote* machine (the
Juju node) at `127.0.0.1`.  Writing `127.0.0.1 kube-galaxy.orchestrator` in
`/etc/hosts` on the Juju machine means every `curl`, `containerd pull`, and other
service call that targets `kube-galaxy.orchestrator` travels through the tunnel
automatically, with no application-level changes.

### Why use `juju ssh` for the tunnel instead of raw `ssh`?

`juju ssh` passes raw OpenSSH options (inserted between the target unit name and an
optional remote command) straight to the underlying `ssh` client.  The command
`juju ssh --no-host-key-checks <unit> -N -R <port>:localhost:<port>` works directly.
This avoids:
- querying `public-address` from `juju status` to build a raw SSH target,
- managing SSH identity files (Juju supplies `~/.ssh/id_rsa` automatically),
- `StrictHostKeyChecking=no` / `UserKnownHostsFile=/dev/null` hacks (replaced by
  `--no-host-key-checks`).

### `juju exec` and `juju scp` are kept for run/put/get

Only the tunnel (connectivity bridging) uses a raw `ssh` process.  Command execution
and file transfer continue to use `juju exec` and `juju scp` because they handle Juju
model auth and unit naming, and do not need to route through the tunnel.

---

## Class: `JujuUnit`

### Constructor

```python
JujuUnit(machine_name: str, role: NodeRole, index: int, tunnel_ports: list[int])
```

| Parameter | Description |
|---|---|
| `machine_name` | Juju unit name, e.g. `kube-galaxy-control-plane/0` |
| `role` | `NodeRole.CONTROL_PLANE` or `NodeRole.WORKER` |
| `index` | Zero-based index within the role |
| `tunnel_ports` | Ports to forward over the SSH reverse tunnel |

`self._tunnel` — holds the `subprocess.Popen` handle for the running SSH tunnel
process, or `None` if the tunnel has not been started or has been stopped.

### `enlist()` sequence

1. Poll `juju status` until workload/juju statuses are `active`/`idle`
   (timeout: `JUJU_PATIENT_TIMEOUT`, default 900 s).
2. `_enable_root_ssh()` — copy `ubuntu`'s `authorized_keys` to `/root/.ssh/`.
3. `_start_ssh_tunnel(self._tunnel_ports)` — open the reverse tunnel (see below).
4. `update_etc_hosts(orchestrator_ip)` — write `127.0.0.1 kube-galaxy.orchestrator`
   (or the orchestrator IP passed in from the provider).

Steps 3 and 4 are ordered deliberately: the tunnel must be open before any component
attempts to connect to `kube-galaxy.orchestrator`, which could happen immediately
after enlist returns.

### `open_tunnel() -> None`

Idempotent tunnel start.  If `self._tunnel` is already set and the process is still
running (`poll() is None`), returns immediately.  Otherwise spawns a background
`juju ssh` process:

```
juju ssh --no-host-key-checks <unit>
    -N
    -R <port>:localhost:<port>   (repeated for each port)
```

- `--no-host-key-checks` — Juju's own flag; skips host-key verification for ephemeral
  machines whose keys are not in the orchestrator's `known_hosts`.
- `-N` — no remote command; keeps the tunnel alive without a shell.
- Juju supplies the correct SSH identity and resolves the unit's address automatically.
- If `self._tunnel_ports` is empty the method returns immediately without spawning.

Used both from `enlist()` (first process: `setup_cluster`) and from
`JujuUnitProvider.open_tunnels()` (subsequent processes: test, cleanup, status).

### `tunnel_alive() -> bool`

Returns `True` if `self._tunnel` is not `None` and `self._tunnel.poll() is None`
(the subprocess is still running).  Used by the verify/status command to report tunnel
health per unit.

### `stop_tunnel() -> None`

Sends `SIGTERM` to the tunnel process and waits up to 5 seconds for it to exit;
falls back to `SIGKILL`.  Safe to call when `self._tunnel is None` (no-op).

---

## Class: `JujuUnitProvider`

### Constructor

```python
JujuUnitProvider(node_cfg: NodesConfig, image: str, tunnel_ports: list[int])
```

`tunnel_ports` is derived by `provider_factory()` in `provider.py`:

```python
tunnel_ports = [ArtifactServer.DEFAULT_PORT]          # always forward artifact server
if manifest.artifact.registry.enabled:
    tunnel_ports.append(manifest.artifact.registry.port)
```

### `orchestrator_ip() -> str`

Returns `"127.0.0.1"` unconditionally.  Juju nodes always reach orchestrator services
through the reverse tunnel, so this is always the correct address to write into
`/etc/hosts` and to pass to `RegistryMirror`.

### `provision()` / `locate()`

Both return a `JujuUnit` constructed with `tunnel_ports=self._tunnel_ports`.
`provision()` calls `juju deploy ch:ubuntu` (index 0) or `juju add-unit` (index > 0).
`locate()` inspects `juju status` and maps sorted unit names to indices.

### `open_tunnels()` / `stop_tunnels()`

Convenience helpers that iterate all tracked units and call `open_tunnel()` /
`stop_tunnel()` on each.  Called by CLI commands that are not `setup_cluster` (which
uses `enlist()` instead).

```python
def open_tunnels(self) -> None:
    for unit in self._units:
        if isinstance(unit, JujuUnit):
            unit.open_tunnel()

def stop_tunnels(self) -> None:
    for unit in self._units:
        if isinstance(unit, JujuUnit):
            unit.stop_tunnel()
```

The base `UnitProvider` provides no-op default implementations so callers in
`cluster.py` / command handlers can call them unconditionally regardless of provider.

### `deprovision(unit)`

Calls `unit.stop_tunnel()` first (safe no-op if tunnel was never started), then issues
`juju remove-application --force --no-prompt` (index 0) or
`juju remove-unit --force --no-prompt`.

### `_cloud_type() -> str`

Inspects `juju models --format json` to determine the cloud substrate of the active
model (`lxd`, `microstack`, `openstack`, etc.).  Used in `provision()` to decide
whether to pass `virt-type=virtual-machine` in the constraints — required when Juju
itself runs on LXD/MicroStack to get a real VM rather than a system container.

---

## Interaction with Other Components

### `cluster.py` — `setup_cluster()`

```python
provider = provider_factory(manifest)       # returns JujuUnitProvider
units = provider.provision_all()
for unit in units:
    unit.enlist(orchestrator_ip=provider.orchestrator_ip())   # opens tunnel + writes /etc/hosts

mirror = RegistryMirror(reg_cfg, orchestrator_ip=provider.orchestrator_ip())
# ... setup hooks ...
provider.stop_tunnels()   # tunnels no longer needed once setup completes
```

### `cluster.py` — `teardown_cluster()`

```python
provider = provider_factory(manifest)
units = provider.locate_all()            # fresh JujuUnit objects, no live tunnels
provider.open_tunnels()                  # re-establish for cleanup hooks
# ... teardown hooks (kubeadm reset, service stop, etc.) ...
provider.stop_tunnels()                  # close before deprovision
_deprovision(provider, force)
```

### `cmd/test.py` — `spread()`

```python
provider = provider_factory(manifest)
lead_unit = provider.locate(NodeRole.CONTROL_PLANE, 0)
provider.open_tunnels()                  # nodes may pull images during tests
# ... run spread tests ...
provider.stop_tunnels()
```

### `cmd/status.py` — `status()`

```python
provider = provider_factory(manifest)
units = provider.locate_all()
provider.open_tunnels()
# ... health checks ...
_print_tunnel_status(provider)           # Juju-only: report per-unit tunnel health
provider.stop_tunnels()
```

### `RegistryMirror`

`RegistryMirror.registry_address(local=True)` now uses the stored `orchestrator_ip`
instead of calling `detect_ip()` at the time of the skopeo call.  For Juju this means
skopeo (running on the orchestrator) connects to `127.0.0.1:<port>` — which is where
the local registry actually listens, so this is correct.

### `ArtifactServer`

The artifact server binds to `0.0.0.0`; the `base_url` it advertises uses
`URLs.ORCHESTRATOR_HOST`.  Units resolve this hostname via the `/etc/hosts` entry
written by `update_etc_hosts()`.  No changes to `ArtifactServer` are needed beyond
the `DEFAULT_PORT = 8765` class constant (used by `provider_factory` to build
`tunnel_ports`).

### `kube-galaxy verify` / `status` tunnel reporting

When the provider is `JujuUnitProvider`, `status()` calls a `_print_tunnel_status()`
helper that iterates located units and calls `unit.tunnel_alive()` on each:

```
[Juju Tunnel Status]
  kube-galaxy-control-plane/0  ✓ alive
  kube-galaxy-worker/0         ✓ alive
  kube-galaxy-worker/1         ✗ dead
```

This is implemented by checking `isinstance(provider, JujuUnitProvider)` in the
status command; the base `UnitProvider` has no equivalent method.

---

## Failure Modes

| Scenario | Behaviour |
|---|---|
| Juju machine never reaches `active/idle` | `ClusterError` after `JUJU_PATIENT_TIMEOUT` (900 s) |
| `juju ssh` cannot resolve unit address | `_start_ssh_tunnel` process exits immediately; subsequent `download()` / image pull calls time out, surfacing a network error |
| SSH tunnel process exits unexpectedly | Subsequent `download()` / image pull calls on the unit will time out; cluster setup fails with a network error |
| `stop_tunnel()` called on a fresh `locate_all()` unit | `self._tunnel is None` → no-op; safe |
| `open_tunnel()` called when tunnel is already alive | `poll() is None` → no-op; idempotent |
| `tunnel_ports=[]` | No SSH process is spawned; `kube-galaxy.orchestrator` is still written to `/etc/hosts` (pointing to `127.0.0.1`) but no ports are forwarded — only valid if neither artifact server nor registry mirror is used |

---

## Testing

Unit tests for `JujuUnit` tunnel behaviour live in `tests/unit/test_units.py`:

- `test_juju_unit_open_tunnel_spawns_process` — patches `subprocess.Popen`, verifies
  `juju ssh --no-host-key-checks` command includes all expected `-R` flags.
- `test_juju_unit_open_tunnel_noop_on_empty_ports` — verifies no process is spawned
  when `tunnel_ports=[]`.
- `test_juju_unit_open_tunnel_idempotent` — verifies a second `open_tunnel()` call does
  not spawn a new process when `poll()` returns `None`.
- `test_juju_unit_tunnel_alive_true` — `poll()` returns `None` → `tunnel_alive()` is `True`.
- `test_juju_unit_tunnel_alive_false_when_none` — no tunnel set → `False`.
- `test_juju_unit_tunnel_alive_false_when_exited` — `poll()` returns `0` → `False`.
- `test_juju_unit_stop_tunnel_terminates` — verifies `stop_tunnel()` terminates the
  mock process.
- `test_juju_unit_stop_tunnel_noop` — verifies `stop_tunnel()` is safe when
  `self._tunnel is None`.
- `test_juju_provider_orchestrator_ip` — asserts `JujuUnitProvider.orchestrator_ip()`
  returns `"127.0.0.1"`.
- `test_juju_provider_open_tunnels_calls_each_unit` — verifies `open_tunnels()` calls
  `open_tunnel()` on every tracked `JujuUnit`.
- `test_juju_provider_stop_tunnels_calls_each_unit` — same for `stop_tunnels()`.
