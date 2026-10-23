## Why immutable containers

An attacker who gets code execution in a container usually wants to persist:
drop a binary, change a config file, install tools. With
`readOnlyRootFilesystem: true` the container's image layers are mounted
read-only, so none of that works, and a restart always returns to the image's
exact content. Applications that need scratch space get explicit, disposable
volumes, typically `emptyDir` (optionally `medium: Memory`) for `/tmp`,
caches or PID files.

`privileged: true` removes almost every isolation boundary: all capabilities
(including `CAP_SYS_ADMIN`, bit 21 in `CapEff`), every host device under
`/dev`, and the ability to remount filesystems. A privileged container can
undo `readOnlyRootFilesystem` and often escape to the node. Immutability
therefore needs both settings.

Runtime-security tools (Falco and similar) build on the same idea: when
containers are immutable, any write to a binary path or a spawned shell is an
alert, not noise.

## How to recognise problems in production

- After switching on read-only root: `CrashLoopBackOff` with
  `Read-only file system` in the logs. Find the paths the app writes
  (logs, `/tmp`, caches) and mount `emptyDir` there.
- Some images write to `/var/run`, `/var/cache/nginx` or similar at start-up;
  the official nginx image needs several such mounts.
- `kubectl get pods -o jsonpath` over `securityContext.privileged` finds
  privileged workloads; Pod Security `baseline` blocks them per namespace.

## Alternatives

- Delete the privileged workload if it has no reason to exist. In the CKS
  exam, "delete non-immutable Pods" is a common phrasing of this task.
- Removing the `privileged` field entirely (JSON patch `remove`) is
  equivalent to setting it to `false`.
- Pod Security Admission `restricted` plus a policy that requires
  `readOnlyRootFilesystem` enforces this for every new Pod.
