# Single-Node Kubeadm Cluster Without CNI

> ⚠️ **Note**: This manifest is designed for **manual testing only** and is excluded from automated CI/CD workflows because the cluster nodes will remain in `NotReady` state without a CNI plugin.

## Overview

This manifest creates a minimal, single-node Kubernetes cluster using kubeadm **without any Container Network Interface (CNI)** plugin. This is useful for:

- Testing core Kubernetes components in isolation
- Understanding what Kubernetes provides out-of-the-box without networking
- Bootstrapping a cluster before adding custom networking solutions
- Educational purposes to learn about Kubernetes networking requirements

## What's Included

This manifest includes only the **essential core Kubernetes components**:

### Container Runtime
- **containerd** (v2.2.1): Container runtime
- **runc** (v1.3.4): OCI runtime

### Kubernetes Core Binaries
- **kubeadm** (v1.35.0): Cluster bootstrapping tool
- **kubelet** (v1.35.0): Node agent
- **kubectl** (v1.35.0): CLI tool

### Kubernetes Control Plane Components
- **kube-apiserver**: API server
- **kube-controller-manager**: Controller manager
- **kube-scheduler**: Scheduler
- **kube-proxy**: Network proxy
- **pause**: Infrastructure container

### Supporting Components
- **etcd** (v3.5.26): Distributed key-value store for cluster state
- **etcdctl**: etcd CLI tool
- **coredns** (v1.13.1): DNS server for service discovery

## What's NOT Included

❌ **No CNI plugins** - The cluster will not have pod-to-pod networking
❌ **No network overlay** (Calico, Flannel, Weave, etc.)
❌ **No worker nodes** - Single control-plane node only

## Cluster Behavior

Without a CNI plugin:
- ✅ The cluster will start successfully
- ✅ Core components (API server, etcd, scheduler, controller-manager) will run
- ✅ You can create pods and deployments
- ⚠️ Pods will remain in `ContainerCreating` or `Pending` state waiting for networking
- ⚠️ Pods cannot communicate with each other
- ⚠️ Services will not work (except host-network pods)
- ✅ Host-network pods (using `hostNetwork: true`) will work
- ✅ Static pods on the control plane will work

## Usage

### 1. Validate the Manifest

```bash
kube-galaxy validate manifests
```

### 2. Inspect the Manifest

```bash
kube-galaxy test-manifest manifests/single-node-no-cni.yaml
```

### 3. Set Up the Cluster

```bash
kube-galaxy test setup --manifest manifests/single-node-no-cni.yaml
```

This will:
1. Install all components (containerd, kubeadm, kubelet, etc.)
2. Initialize the cluster with `kubeadm init`
3. Configure kubectl access
4. **NOT** install any CNI plugin

### 4. Verify Cluster State

After setup, you can verify the cluster is running:

```bash
kubectl get nodes
# Expected: Node will be NotReady (no CNI)

kubectl get pods -n kube-system
# Expected: Core components running, but networking pods missing

kubectl get componentstatuses
# Expected: All components healthy
```

### 5. Observe CNI Requirement

Try creating a simple pod:

```bash
kubectl run test-pod --image=nginx
kubectl get pods
# Expected: Pod stuck in ContainerCreating or Pending
```

Check pod events:
```bash
kubectl describe pod test-pod
# Expected: Event showing "network plugin is not ready"
```

### 6. (Optional) Add CNI Later

You can add a CNI plugin after the cluster is running:

```bash
# Example: Install Calico
kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml

# Watch nodes become Ready
kubectl get nodes -w
```

### 7. Clean Up

```bash
kube-galaxy cleanup all
```

## Use Cases

### 1. Testing Core Components
Test custom builds of Kubernetes components without networking interference.

### 2. Learning Kubernetes Networking
Understand what Kubernetes provides by default and what the CNI adds.

### 3. Custom CNI Development
Bootstrap a cluster to test your own CNI implementation.

### 4. Debugging Control Plane Issues
Isolate control plane problems from networking issues.

## Configuration Details

- **Kubernetes Version**: 1.35.0
- **Nodes**: 1 control-plane, 0 workers
- **Service CIDR**: Not configured (no CNI)
- **Pod CIDR**: Not configured (no CNI)
- **Storage**: local-path provisioner
- **Security**: RBAC enabled, network policies disabled, baseline pod security

## Limitations

1. **No pod-to-pod networking**: Pods cannot communicate across the cluster
2. **No services**: ClusterIP services won't work without CNI
3. **No ingress**: Cannot route external traffic to pods
4. **Single node only**: No multi-node cluster support without networking
5. **CoreDNS may not work**: DNS pods may fail without networking

## Expected Node State

```bash
$ kubectl get nodes
NAME           STATUS     ROLES           AGE   VERSION
control-plane  NotReady   control-plane   1m    v1.35.0
```

The node will show `NotReady` because the kubelet cannot confirm the node is ready without a functioning CNI.

## Next Steps

After validating that the core cluster components work:
1. Install a CNI plugin (Calico, Flannel, Cilium, etc.)
2. Verify node transitions to `Ready` state
3. Test pod networking and services

## References

- [Kubernetes CNI Documentation](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/)
- [kubeadm Installation Guide](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/)
- [CNI Specification](https://github.com/containernetworking/cni/blob/master/SPEC.md)
