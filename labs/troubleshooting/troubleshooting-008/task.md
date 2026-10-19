After a maintenance window on the control plane node `{{node.controlplane}}`,
`kubectl` no longer works:

```
The connection to the server ... was refused
```

Bring the Kubernetes API back and make sure the cluster is healthy (all nodes
`Ready`). The kubelet and etcd on the node are fine. Do not reinstall the
cluster.

Node access: `cka ssh {{node.controlplane}}`.
