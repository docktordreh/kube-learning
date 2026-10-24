## Pod Security Admission

The built-in Pod Security Admission controller checks Pods against three
standard profiles: `privileged` (anything), `baseline` (blocks known privilege
escalations such as hostPath, host namespaces, privileged containers) and
`restricted` (current hardening best practice). Namespace labels choose the
profile per mode:

- `pod-security.kubernetes.io/enforce=<level>` rejects violating Pods,
- `audit=<level>` records violations in the audit log,
- `warn=<level>` returns warnings to the client,
- optional `...-version=v1.37` pins the profile definition; `latest` is the
  default.

Admission runs when Pods are **created**. Labelling a namespace does not touch
running Pods; it only warns about them. Controllers notice on their next Pod
creation. A Deployment whose template violates `enforce` shows `FailedCreate`
events on its ReplicaSet, and its Pods never appear.

`restricted` requires, for every container: `runAsNonRoot: true`,
`allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]` (only
`NET_BIND_SERVICE` may be added), a `RuntimeDefault` or `Localhost` seccomp
profile, and no hostPath or host namespaces.

The check reads the effect inside the container: `CapEff` all zero (no
capabilities), `NoNewPrivs: 1` (escalation blocked) and `Seccomp: 2` (a
seccomp filter is active, here the runtime's default profile).

## How to recognise problems in production

- After enabling `enforce`, Deployments stop scaling or rolling out:
  `kubectl describe rs` shows `violates PodSecurity "restricted:latest"`.
  Roll out `warn` and `audit` first to find violators safely.
- Images that run as root fail with `runAsNonRoot` even when compliant on
  paper: set `runAsUser` or build the image with a non-root `USER`.
- System namespaces (`kube-system`, CNI, CSI) usually need `privileged`;
  restricted cluster-wide defaults need exemptions.

## Alternatives

- Set the fields at container level instead of Pod level (both are accepted).
- Cluster-wide defaults and exemptions go into the `PodSecurity` admission
  configuration file of the API server.
- Policy engines (Kyverno, Gatekeeper) or ValidatingAdmissionPolicy express
  rules beyond the three profiles.
