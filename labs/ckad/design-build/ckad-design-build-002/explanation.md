## Why a DaemonSet

A Deployment asks for N Pods anywhere. The scheduler may stack two on one node
and leave another node empty, and N does not follow the node count. A
DaemonSet asks for one Pod per eligible node. Its controller adds a Pod when a
node joins and removes it when the node leaves. That fits node agents: log
shippers, monitoring exporters, CNI and CSI node plugins, kube-proxy.

"Eligible" follows normal scheduling rules: `nodeSelector`, node affinity and
taints. Control-plane nodes are tainted
`node-role.kubernetes.io/control-plane:NoSchedule`, so an agent that must
cover them needs that toleration. DaemonSet Pods automatically tolerate the
`not-ready`, `unreachable`, disk-, memory- and PID-pressure and unschedulable
taints, but not the control-plane taint.

The hostPath volume gives the Pod a node directory. Mounting it read-only
(`readOnly: true` on the volumeMount) keeps a compromised or buggy agent from
altering the node's logs. hostPath is powerful: Pod Security `baseline`
already forbids it, so such agents usually run in a dedicated, privileged
namespace.

## How to recognise problems in production

- `DESIRED` lower than the node count in `kubectl get ds`: a taint or selector
  excludes nodes. Compare `kubectl describe node` taints with the Pod
  tolerations.
- Agents stuck `Pending` on one node: that node lacks resources. DaemonSet
  Pods compete like any other Pod; a PriorityClass helps.
- An update replaces Pods node by node (`RollingUpdate`, `maxUnavailable: 1`);
  with `OnDelete` nothing changes until Pods are deleted.

## Alternatives

- `operator: Exists` without a key tolerates every taint. That is common for
  infrastructure DaemonSets, but broader than needed here.
- Creating the DaemonSet first and deleting the Deployment afterwards keeps
  log collection running during the switch, at the cost of briefly running
  both.
