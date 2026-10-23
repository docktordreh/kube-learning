## What was wrong

`/var/lib/kubelet/config.yaml` pointed `authentication.x509.clientCAFile` at
`{{bad_ca}}`, which does not exist. The kubelet validates this file at
startup and exits (`unable to load client CA file`). systemd restarted it
every second (`Restart=always`), so `systemctl status` showed it flapping
between `activating` and `failed`.

Without a running kubelet, nobody renewed the node's **Lease** in
`kube-node-lease`. After the node-monitor grace period (about 40–50 s) the node
lifecycle controller set `Ready=Unknown` ("Kubelet stopped posting node
status") and added `node.kubernetes.io/unreachable` taints. Pods there are
evicted after their 300 s toleration.

## Method

1. `kubectl describe node`: condition `Ready=Unknown` + reason → the kubelet
   is not reporting. Investigate the node itself, not the API.
2. On the node: `systemctl status kubelet`, `journalctl -u kubelet -e`.
3. Configuration sources, in precedence order: the systemd unit and drop-ins
   (`systemctl cat kubelet`), `/var/lib/kubelet/kubeadm-flags.env`,
   `/etc/default/kubelet`, then the config file given by `--config`.
4. Fix, `systemctl restart kubelet`, and watch the node return.

## Other common causes of NotReady

A stopped or disabled kubelet (`systemctl enable --now kubelet`), a container
runtime that is down (`systemctl status containerd`, `crictl info`), expired
kubelet client certificates, a missing CNI configuration (`NetworkReady=false`),
swap enabled without `failSwapOn: false`, and disk or memory pressure.
