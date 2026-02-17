"""
Component installation and management modules.

Components inherit from ComponentBase and override the lifecycle hooks they need.
"""

from kube_galaxy.pkg.components._base import ComponentBase
from kube_galaxy.pkg.components.containerd import Containerd
from kube_galaxy.pkg.components.etcd import Etcd
from kube_galaxy.pkg.components.kube_apiserver import KubeAPIServer
from kube_galaxy.pkg.components.kube_controller_manager import KubeControllerManager
from kube_galaxy.pkg.components.kube_proxy import KubeProxy
from kube_galaxy.pkg.components.kube_scheduler import KubeScheduler
from kube_galaxy.pkg.components.kubeadm import Kubeadm
from kube_galaxy.pkg.components.kubectl import Kubectl
from kube_galaxy.pkg.components.kubelet import Kubelet
from kube_galaxy.pkg.components.pause import Pause
from kube_galaxy.pkg.components.runc import Runc

__all__ = [
    "COMPONENTS",
    "ComponentBase",
]


# Simple mapping of component names to classes
COMPONENTS: dict[str, type[ComponentBase]] = {
    "containerd": Containerd,
    "etcd": Etcd,
    "kubeadm": Kubeadm,
    "kube-apiserver": KubeAPIServer,
    "kube-controller-manager": KubeControllerManager,
    "kube-proxy": KubeProxy,
    "kube-scheduler": KubeScheduler,
    "kubectl": Kubectl,
    "kubelet": Kubelet,
    "pause": Pause,
    "runc": Runc,
}
