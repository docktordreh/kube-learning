## Concepts

Kustomize is built into kubectl (`kubectl kustomize`, `kubectl apply -k`). It
renders plain YAML by applying **transformers** to resources, with no
templating:

| field | effect |
|---|---|
| `resources` | files or directories (other kustomizations) to include |
| `namespace` | sets `metadata.namespace` on every namespaced object |
| `namePrefix` / `nameSuffix` | renames objects *and* updates references (Service selectors stay intact, ConfigMap refs are rewritten) |
| `labels` | adds labels. `includeSelectors: true` also changes selectors (immutable on Deployments, so be careful); `includeTemplates: true` adds them to Pod templates only |
| `replicas` | overrides `spec.replicas` by object name (pre-prefix name) |
| `images` | rewrites image name/tag/digest wherever the image is used |

`commonLabels` still works but is deprecated in favour of `labels`, because it
always rewrites selectors.

## Helm vs Kustomize

Helm packages templated charts with release tracking (`helm install/upgrade/rollback`).
Kustomize patches plain manifests declaratively. Both appear in the CKA
curriculum. Many teams render Helm charts and then post-process them with
Kustomize.
