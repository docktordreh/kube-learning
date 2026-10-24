## Secret delivery choices

Kubernetes Secret data can reach a container through an environment variable,
a mounted volume, or an API request made with a ServiceAccount. Environment
variables are convenient but easy to expose through debug output, process
inspection, crash reports, and accidental logging. A volume keeps the value
out of the process environment and gives the application a file interface.

The kubelet materialises each Secret key as a file below the mount path. The
volume is updated when the Secret changes, although applications must reopen
the file or reload it to observe the new value. `readOnly: true` prevents the
container from changing the mounted data. `defaultMode: 0400` limits reads to
the container user; choose a mode compatible with the image's user and group.

The Secret is still base64-encoded storage, not encryption by itself. Enable
encryption at rest and restrict Secret reads with RBAC. Avoid granting a
workload access to the Kubernetes API when a projected volume is sufficient.

## Production symptoms

- A password appears in `kubectl exec ... -- env`, a debug dump, or a crash
  report: remove the environment reference and mount the Secret as a file.
- The file is missing after a rollout: check the volume name, `secretName`,
  key name, and Pod events.
- A file permission error follows `defaultMode: 0400`: verify the process UID
  and use `fsGroup` only when the workload needs group access.

## Alternatives

Projected volumes can combine several Secret and ConfigMap sources. External
secret managers can sync short-lived credentials, but still require careful
RBAC and rotation handling. Never put Secret values in an image, ConfigMap, or
plain-text manifest committed to source control.
