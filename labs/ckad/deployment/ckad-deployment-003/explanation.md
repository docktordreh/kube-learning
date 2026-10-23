## How Helm tracks releases

A release is one installation of a chart under a name, in one namespace.
Helm 3 and 4 keep no server component. Each revision of a release is a Secret
`sh.helm.release.v1.<release>.v<revision>` in the release's namespace, labelled
`owner=helm`, `name=<release>`, `status=deployed|superseded|...`. That is why
`helm list` needs `-A` (or the right `-n`) to find a release, and why deleting
the namespace also "removes" every release in it.

- `helm upgrade` renders the new chart version with the merged values, applies
  the difference and records revision N+1. The old revision stays for
  `helm rollback`.
- `helm uninstall` deletes the objects the release created and its history.
- Values: chart defaults < `-f file.yaml` < `--set key=value`. An upgrade
  without `--reuse-values` or `-f` starts from the new chart's defaults again,
  so values set at install time must be passed again.

Chart version (`1.1.0`, the package) and app version (`1.31`, the software)
are independent. `helm list` shows both.

## How to recognise problems in production

- "cannot re-use a name that is still in use": the release exists, perhaps in
  another namespace or in a failed state. Check `helm list -A --all`.
- A release stuck in `pending-install` or `pending-upgrade` after an interrupted
  command blocks further upgrades. `helm rollback` or `helm uninstall` clears it.
- `kubectl edit` changes on Helm-managed objects are overwritten by the next
  upgrade. Put them in values instead.

## Alternatives

- `helm upgrade --install` creates or upgrades in one idempotent command.
- `-f values.yaml` instead of `--set` keeps the configuration in a file you
  can review.
- From a repository: `helm repo add`, then `helm upgrade <release> repo/chart
  --version 1.1.0`. This lab uses local packages so it runs offline.
