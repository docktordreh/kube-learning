## Concepts

- **Environment variables** from a ConfigMap or Secret (`valueFrom` or
  `envFrom`) are resolved **once, at container start**. Changing the ConfigMap
  later does not change a running process's environment. You need a new Pod
  (`kubectl rollout restart`).
- **Volumes** from ConfigMaps/Secrets project each key as a file. The kubelet
  refreshes them eventually (except with `subPath` mounts), so file-based
  configuration can be hot-reloaded by the app.
- Secret volumes are tmpfs-backed. `readOnly: true` on the mount makes the
  intent explicit. Secret volumes use mode 0644 by default; tighten it with
  `defaultMode`.
- Secrets are only base64-encoded in the API, not encrypted. Protect them with
  RBAC and enable encryption at rest on the API server.

## Alternatives

`envFrom: [{configMapRef: {name: {{app}}-settings}}]` imports every key as an
environment variable, and the grader accepts it. Editing the Deployment
interactively (`kubectl edit`) works just as well as the patch.

## In production

`CreateContainerConfigError` means a referenced ConfigMap, Secret or key does
not exist. `kubectl describe pod` names it. Mark references `optional: true`
only when the app really copes without them.
