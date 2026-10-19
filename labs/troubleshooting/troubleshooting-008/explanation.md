## What was wrong

`--etcd-servers` in the kube-apiserver static Pod manifest pointed to
`{{fault}}`. etcd only serves clients on `https://127.0.0.1:2379`. Port 2380 is
the **peer** port, and plain `http://` fails the TLS handshake. The API server
cannot start without its storage, so its container exited, the kubelet
restarted it with back-off, and every kubectl call was refused.

## Method for a dead control plane

1. kubectl is blind. Go to the control plane node.
2. Ask the runtime: `crictl ps -a` (`-a` shows exited containers),
   `crictl logs <id>`. The files under `/var/log/pods/` and
   `/var/log/containers/` contain the same output.
3. Static Pods: `/etc/kubernetes/manifests/*.yaml` (`staticPodPath` in the
   kubelet config). The kubelet watches that directory. Saving a fixed file
   recreates the Pod, so there is nothing to "apply".
4. If the container never starts at all (a YAML error), check
   `journalctl -u kubelet` for the parse error.

## Traps

- Any `*.yaml` in the manifests directory is loaded. A backup file such as
  `kube-apiserver.yaml.bak.yaml` starts a second API server. Keep backups
  elsewhere.
- After the fix, nodes may briefly show NotReady while their leases catch up.
  Wait for them before declaring success.
