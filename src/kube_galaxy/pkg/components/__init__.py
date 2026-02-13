"""
Component installation and management modules.

Components inherit from ComponentBase and override the lifecycle hooks they need.
"""

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.components.cluster_autoscaler import ClusterAutoscaler
from kube_galaxy.pkg.components.cni_plugins import CNIPlugins
from kube_galaxy.pkg.components.containerd import Containerd
from kube_galaxy.pkg.components.coredns import CoreDNS
from kube_galaxy.pkg.components.etcd import Etcd
from kube_galaxy.pkg.components.etcdctl import Etcdctl
from kube_galaxy.pkg.components.external_attacher import ExternalAttacher
from kube_galaxy.pkg.components.external_provisioner import ExternalProvisioner
from kube_galaxy.pkg.components.kube_apiserver import KubeAPIServer
from kube_galaxy.pkg.components.kube_controller_manager import KubeControllerManager
from kube_galaxy.pkg.components.kube_proxy import KubeProxy
from kube_galaxy.pkg.components.kube_scheduler import KubeScheduler
from kube_galaxy.pkg.components.kubeadm import Kubeadm
from kube_galaxy.pkg.components.kubectl import Kubectl
from kube_galaxy.pkg.components.kubelet import Kubelet
from kube_galaxy.pkg.components.node_problem_detector import NodeProblemDetector
from kube_galaxy.pkg.components.pause import Pause
from kube_galaxy.pkg.components.runc import Runc

__all__ = [
    "COMPONENTS",
    "ComponentBase",
]


# Simple mapping of component names to classes
COMPONENTS: dict[str, type[ComponentBase]] = {
    "cluster-autoscaler": ClusterAutoscaler,
    "cni-plugins": CNIPlugins,
    "containerd": Containerd,
    "coredns": CoreDNS,
    "etcd": Etcd,
    "etcdctl": Etcdctl,
    "external-attacher": ExternalAttacher,
    "external-provisioner": ExternalProvisioner,
    "kubeadm": Kubeadm,
    "kube-apiserver": KubeAPIServer,
    "kube-controller-manager": KubeControllerManager,
    "kube-proxy": KubeProxy,
    "kube-scheduler": KubeScheduler,
    "kubectl": Kubectl,
    "kubelet": Kubelet,
    "node-problem-detector": NodeProblemDetector,
    "pause": Pause,
    "runc": Runc,
}
