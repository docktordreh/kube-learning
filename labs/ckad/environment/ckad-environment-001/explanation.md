## How the two security contexts combine

`spec.securityContext` sets defaults for every container in the Pod: user
(`runAsUser`), primary group (`runAsGroup`), `runAsNonRoot`, `fsGroup`,
supplemental groups and seccomp. `spec.containers[].securityContext` overrides
the overlapping fields for one container and adds container-only ones such as
`readOnlyRootFilesystem`, `allowPrivilegeEscalation` and `capabilities`.

`runAsNonRoot: true` is a check, not a setting: the kubelet refuses to start a
container whose effective UID is 0. With an explicit `runAsUser` the check
passes. Without one, it depends on the image's `USER`, and the Pod fails with
`CreateContainerConfigError` for root images such as busybox.

A read-only root filesystem stops an attacker or a bug from changing binaries
or configuration. Applications that need scratch space get an `emptyDir`
mounted at `/tmp` or wherever they write.

## How to recognise problems in production

- `CreateContainerConfigError` with "container has runAsNonRoot and image will
  run as root": add `runAsUser` or use a non-root image.
- Applications crashing with "Read-only file system" or "permission denied" after
  hardening: mount `emptyDir` volumes for the paths they write to, and set
  `fsGroup` so the UID can write to volumes.
- Most securityContext fields cannot be changed on a running Pod; recreate it,
  or change the Pod template of the owning Deployment.

## Alternatives

- Setting `runAsUser` and `runAsGroup` on the container instead also yields the
  same identity, but the policy asked for Pod level so every future container
  inherits it.
- Pod Security Admission with the `restricted` level enforces many of these
  rules per namespace instead of per Pod.
