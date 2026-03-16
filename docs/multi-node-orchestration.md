# Multi-Node Orchestration Design

## Status: Planning — implementation starts Monday

---

## Motivation

kube-galaxy currently provisions a single-node Kubernetes cluster on the local machine.
This document captures the agreed design for extending it to support **ephemeral multi-node clusters** — clusters that exist only long enough to run tests (minutes to hours) and are then destroyed.

The CLI entry point (`kube-galaxy setup / test / cleanup`) does not change.
All new complexity is absorbed below that surface.

---

## Key Abstractions

### `Unit`

A `Unit` represents one machine. It exposes three operations:

```python
class Unit(ABC):
    @property
    def name(self) -> str: ...        # stable identifier: "cp-0", "worker-1"

    @property
    def arch(self) -> ArchInfo: ...   # detected from the unit itself (remote uname -m)

    def run(self, cmd, *, check=True, env=None) -> RunResult: ...
    def put(self, local: Path, remote: str) -> None: ...
    def get(self, remote: str, local: Path) -> None: ...
```

Concrete implementations:

| Class | Mechanism | Ephemeral |
|---|---|---|
| `LocalUnit` | wraps existing `shell.run()` | no |
| `SSHUnit` | `subprocess ssh` | no (pre-existing hosts) |
| `LXDUnit` | `lxc exec` / `lxc file push/pull` | yes |
| `MultipassUnit` | `multipass exec` / `multipass transfer` | yes |

`LocalUnit` is the **Null Object** default — existing single-node manifests work with zero changes.

### `UnitProvider`

Owns the _machine lifecycle_, not operations on machines:

```python
class UnitProvider(ABC):
    def provision(self, role: NodeRole, index: int) -> Unit: ...
    def deprovision(self, unit: Unit) -> None: ...
    def deprovision_all(self) -> None: ...
```

Implementations mirror the `Unit` types.
`SSHUnitProvider.deprovision()` is a no-op (hosts are pre-existing).
`LXDUnitProvider.deprovision()` destroys the container/VM.

### `Orchestrator`

Coordinates across all units. **Does not inherit from `Unit`.**

Responsibilities:
- Provision units via `UnitProvider`
- Build per-unit component instance tables
- Drive lifecycle stages across all units
- Own the `ClusterComponentBase` bootstrap handshake (see Stage 5 below)
- Pull `kubeconfig` from the control-plane to the orchestrator machine
- Deprovision units on teardown

The existing flat `instances: dict[str, ComponentBase]` becomes per-unit:
`dict[unit.name, dict[component.name, ComponentBase]]`.

### `ClusterComponentBase`

Abstract base for cluster lifecycle managers (kubeadm, k3s, rke2, …).
The Orchestrator coordinates multi-node join via this interface — **never by knowing the concrete class.**

```python
class ClusterComponentBase(ComponentBase):
    def init_cluster(self) -> None:
        """Bootstrap the initial control-plane on this unit."""

    def generate_join_token(self, role: NodeRole) -> str:
        """Called on the control-plane unit. Returns a single-use token for the
        joining unit. Role distinguishes HA control-plane joins from worker joins."""

    def join_cluster(self, token: str, role: NodeRole) -> None:
        """Called on the joining unit. Consumes the token from generate_join_token()."""

    def pull_kubeconfig(self) -> None:
        """Pull kubeconfig from this unit to the orchestrator's ~/.kube/config."""
```

`KubeadmComponent` implements all four methods.
A future k3s component implements the same interface with a different token format.

### `NodeRole`

```python
class NodeRole(StrEnum):
    CONTROL_PLANE = "control-plane"
    WORKER        = "worker"
```

Lives in `manifest/models.py`. Used by `ClusterComponentBase`, `UnitProvider`, and the Orchestrator.

---

## Manifest Changes

Fully additive — existing manifests with no `provider` block continue to work via `LocalUnit`.

```yaml
name: baseline-k8s-1.35
kubernetes-version: "1.35.0"

# NEW: optional — defaults to provider.type: local
provider:
  type: lxd                # local | lxd | multipass | ssh
  image: ubuntu:24.04      # lxd / multipass: base image to launch
  # For ssh type, list pre-existing hosts:
  # hosts:
  #   - ubuntu@10.0.0.10
  #   - ubuntu@10.0.0.11

nodes:
  control-plane: 1
  worker: 2

# NEW: optional per-component placement (default: all)
components:
  - name: containerd
    placement: all           # every node (default)
  - name: kubeadm
    placement: all           # runs init on CP, join on workers
  - name: kubelet
    placement: all
  - name: calico
    placement: orchestrator  # kubectl apply from orchestrator, not on a node
```

`placement` values: `all`, `control-plane`, `workers`, `orchestrator`.

`ComponentConfig` gains `placement: Placement = Placement.ALL` — a new `StrEnum` in `models.py`.
The loader defaults it to `ALL` when absent.

---

## Component Injection: `unit` Parameter

`ComponentBase.__init__` gains a `unit: Unit` parameter (default `LocalUnit()`):

```python
class ComponentBase:
    def __init__(
        self,
        components: dict[str, "ComponentBase"],
        manifest: Manifest,
        config: ComponentConfig,
        arch_info: ArchInfo,
        unit: Unit | None = None,   # NEW — defaults to LocalUnit
    ) -> None:
        self.unit: Unit = unit or LocalUnit()
```

All helper methods in `ComponentBase` that currently call `shell.run()` or write files
route through `self.unit`:

| Current | Becomes |
|---|---|
| `run([...])` | `self.unit.run([...])` |
| write temp + `sudo cp` | `self.unit.put(local_tmp, remote_path)` |
| `get_arch_info()` at init | `self.unit.arch` (remote-aware, lazy) |

The Orchestrator instantiates each component once **per unit** it is placed on,
passing the appropriate `Unit` instance.

---

## Lifecycle Stages

Stages 1–4 and 6 are straightforward: the Orchestrator runs them across all
placed units, parallelizing across units where the existing `is_parallel` flag allows.

### Stage 5: BOOTSTRAP — the tricky one

Stage 5 must be split into three sub-phases because of the serial
call/response handshake required by `ClusterComponentBase`.

```
5a. Parallel bootstrap of non-ClusterComponentBase components across all units
    (containerd socket up, kubelet enabled, etc.)
    ↓
    *** BARRIER — wait for all units to finish 5a ***
    ↓
5b. Serial ClusterComponentBase handshake (single-threaded, ordered):
      cp_unit.cluster_manager.init_cluster()
      cp_unit.cluster_manager.pull_kubeconfig()
      for each joining unit (in order):
          token = cp_unit.cluster_manager.generate_join_token(unit.role)
          joining_unit.cluster_manager.join_cluster(token, unit.role)
    ↓
    *** BARRIER — all nodes joined ***
    ↓
5c. Parallel bootstrap of orchestrator-placement components
    (CNI manifest apply, ingress controllers, etc.)
    These run from the orchestrator using the kubeconfig pulled in 5b.
```

The exact token exchange pattern the Orchestrator drives:

```
cp.generate_join_token(WORKER) → token_1
worker_0.join_cluster(token_1, WORKER)

cp.generate_join_token(WORKER) → token_2
worker_1.join_cluster(token_2, WORKER)
```

Each token is generated immediately before it is consumed — this is intentional.
Many cluster managers (including `kubeadm`) issue single-use or short-lived tokens,
so tokens must not be pre-generated in bulk.

If a future cluster manager issues long-lived shared tokens, its `generate_join_token()`
implementation can return the same token every time — the Orchestrator loop does not change.

---

## Teardown

For **ephemeral providers** (LXD, Multipass), teardown skips the component-level
`stop` / `delete` / `post_delete` hooks and calls `provider.deprovision_all()` directly.
This makes cleanup near-instant.

For **non-ephemeral providers** (SSH, local), the existing 3-stage teardown runs per-unit.

A provider is considered ephemeral if it provisions machines (`LXDUnitProvider`,
`MultipassUnitProvider`). Pre-existing-machine providers (`SSHUnitProvider`, `LocalUnitProvider`)
are non-ephemeral.

---

## Module Layout

```
src/kube_galaxy/pkg/
├── units/
│   ├── _base.py          # Unit ABC, RunResult dataclass
│   ├── local.py          # LocalUnit — wraps shell.run(), backward compat Null Object
│   ├── ssh.py            # SSHUnit
│   ├── lxdvm.py          # LXDVMUnit
│   ├── multipass.py      # MultipassUnit
│   └── provider.py       # UnitProvider ABC + factory(manifest) → UnitProvider
├── orchestrator.py       # Orchestrator class
├── cluster.py            # Kept for CLI backward compat; delegates to Orchestrator
└── manifest/
    └── models.py         # NodeRole, Placement enums added; ProviderConfig dataclass added
```

---

## Backward Compatibility

A manifest with no `provider` block and `nodes: {control-plane: 1, worker: 0}` behaves
exactly as today:

- `UnitProvider` factory returns `LocalUnitProvider` → yields `LocalUnit`
- `LocalUnit.run()` delegates to existing `shell.run()`
- `LocalUnit.put()` / `get()` are local file copies
- `arch` uses `platform.machine()` as before
- No SSH, no remote provisioning, no regressions

Existing CI workflows (`test-baseline-clusters.yml`) require no changes.

---

## Pitfalls to Revisit During Implementation

1. **`instances` dict scoping.** The `get_cluster_manager()` call inside a component
   must find the cluster manager for *that unit's* instance dict, not a global one.
   Workers must not call `get_cluster_manager()` during bootstrap — only the
   control-plane unit does.

2. **Download arch vs. unit arch.** The DOWNLOAD stage runs on the orchestrator.
   `self.unit.arch` for a remote unit may differ from the orchestrator's arch.
   Components must use `self.unit.arch` (not `get_arch_info()`) when choosing
   which binary to download.

3. **Sudo over SSH.** All component hooks use `sudo`. Remote units need passwordless
   sudo for the connecting user. Validate this eagerly (in `provision()` or
   `pre_install`) and surface a clear error before wasting time on later stages.

4. **Stage 5 barrier implementation.** The Orchestrator must not start 5b until
   all 5a futures have resolved. Use `concurrent.futures.wait(ALL_COMPLETED)` or
   equivalent — do not rely on submission order.

5. **CNI timing.** Calico (and other `placement: orchestrator` components) depend on
   kubeconfig being available (pulled in 5b). The 5c sub-phase must start only after
   `pull_kubeconfig()` completes.

6. **Thread safety in `_run_hook` with multiple units.** The current executor
   parallelizes across components. The new version parallelizes across
   `(unit, component)` pairs. `force` error handling must aggregate all failures
   before raising, not abort on the first one.
