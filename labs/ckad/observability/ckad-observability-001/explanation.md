## Why old manifests stop applying

Kubernetes APIs mature from alpha to beta to GA. Deprecated versions keep
working for a while and are then **removed**. After that the API server no
longer serves the version at all, and `kubectl apply` fails with
`no matches for kind "Deployment" in version "apps/v1beta1"`. Objects that
already exist are unaffected: the server stores them once and serves them in
every version it still knows.

The removals in this manifest:

| object                  | removed version            | removed in | replacement            | field changes                                              |
|-------------------------+----------------------------+------------+------------------------+------------------------------------------------------------|
| Deployment              | apps/v1beta1               | 1.16       | apps/v1                | `spec.selector` required; `rollbackTo` gone                |
| PodDisruptionBudget     | policy/v1beta1             | 1.25       | policy/v1              | an empty selector now selects all Pods                     |
| CronJob                 | batch/v1beta1              | 1.25       | batch/v1               | none                                                       |
| Ingress                 | networking.k8s.io/v1beta1  | 1.22       | networking.k8s.io/v1   | `backend.service.{name,port.number}`; `pathType` required  |

`kubectl convert` (a separate plugin, `kubectl-convert`) reads old manifests
locally and writes current ones. Without `--output-version`, each object goes
to its group's preferred version. Review the output: it fills in defaults
(strategy, `revisionHistoryLimit`, `pathType: ImplementationSpecific`) and
keeps a `deprecated.deployment.rollback.to` annotation for the dropped
`rollbackTo`.

## How to recognise problems in production

- CI or GitOps pipelines fail after a cluster upgrade although nothing changed
  in the repository: old manifests or Helm charts use removed versions.
- Before upgrading, check the `apiserver_requested_deprecated_apis` metric or
  the API server's deprecation warnings (`Warning: ... is deprecated`) for
  clients still using old versions.
- Helm releases whose stored manifests contain removed versions cannot be
  upgraded until they are fixed (`helm mapkubeapis`).

## Alternatives

- Editing by hand is fine for small files. `kubectl explain --api-version`
  and the deprecation guide list the required changes.
- `kubectl apply --dry-run=server` validates against the server, including
  admission, before you apply for real.
