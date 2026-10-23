## What each setting does

- `runAsUser` sets the UID of the container's processes. Without it, busybox
  runs as root (UID 0).
- `allowPrivilegeEscalation: false` makes the runtime set the kernel's
  `no_new_privs` flag. setuid binaries and file capabilities can then no
  longer raise privileges. `/proc/<pid>/status` shows it as `NoNewPrivs: 1`.
- `capabilities.add` extends the container's capability **bounding set**, the
  upper limit any process in the container can ever hold. containerd already
  grants `NET_BIND_SERVICE` and `NET_RAW` by default; `NET_ADMIN` is new.

Note the interaction: a non-root process does not get capabilities in its
effective set just because they are in the bounding set (`CapEff` stays 0 for
UID {{uid}}). Adding capabilities pays off for root processes, or for binaries
with file capabilities. That is why hardened workloads usually combine
`capabilities: {drop: ["ALL"], add: [...only what is needed]}` with a non-root
user.

Changing the Pod template triggers a rolling update: new Pods with the
new securityContext replace the old ones while the Deployment keeps serving.

## How to recognise problems in production

- `Operation not permitted` for network configuration (`ip link`, iptables)
  means a missing `NET_ADMIN`; for raw sockets (`ping`) a missing `NET_RAW`.
- Binding to a port below 1024 as non-root fails without
  `NET_BIND_SERVICE`, often visible as "permission denied" on listen.
- Pod Security Admission `restricted` rejects Pods that add capabilities other
  than `NET_BIND_SERVICE` or allow privilege escalation.

## Alternatives

- `kubectl edit deployment` or `kubectl patch` change the live object, but the
  task also asked for the manifest on disk. Keeping the file as the source of
  truth is the reproducible way.
- Pod-level `securityContext.runAsUser` sets the user too; capabilities and
  `allowPrivilegeEscalation` exist only at container level.
