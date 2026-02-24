"""
CoreDNS component installation and management.

CoreDNS is used as the DNS server for Kubernetes clusters.
"""

import json
import shlex

from kube_galaxy.pkg.components import ComponentBase, register_component
from kube_galaxy.pkg.utils.shell import run


@register_component("coredns")
class CoreDNS(ComponentBase):
    def bootstrap_hook(self) -> None:
        """Patch coredns deployment

        This is needed to allow coredns to run with readOnlyRootFilesystem=false
        which is required for certain versions of coredns that kubeadm may use.
        The patch modifies the coredns deployment to set the securityContext of
        the coredns container to allow read/write access to the root filesystem.

        spec.template.spec.containers[0].securityContext.readOnlyRootFileystem=false
        """
        op = [
            {
                "op": "replace",
                "path": "/spec/template/spec/containers/0/securityContext/readOnlyRootFilesystem",
                "value": False,
            }
        ]
        cmd = shlex.split("kubectl patch deployment/coredns -n kube-system --type='json' -p")
        run([*cmd, json.dumps(op)], check=True)
