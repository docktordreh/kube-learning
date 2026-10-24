## Concepts

A **StorageClass** describes *how* to provision volumes dynamically:

- `provisioner`: the driver that creates volumes (a CSI driver name, or here
  local-path-provisioner);
- `reclaimPolicy`: copied into every PV it creates. `Delete` (the default)
  destroys the data with the claim; `Retain` leaves a `Released` PV behind for
  an admin;
- `volumeBindingMode`: `Immediate` provisions as soon as the claim exists.
  `WaitForFirstConsumer` waits until a Pod is scheduled, so topology-bound
  storage (local disks, zonal cloud disks) ends up where the Pod runs;
- `allowVolumeExpansion`: lets claims grow by editing `spec.resources.requests.storage`.

The default class is marked by the annotation
`storageclass.kubernetes.io/is-default-class: "true"`. If more than one class
carries it, the newest one is used for claims without a class. Avoid that
ambiguity.

## In production

Retained PVs accumulate silently and keep consuming disk. Audit them with
`kubectl get pv | grep Released`. For databases, `Retain` plus backups is the
usual choice. For scratch space, use `Delete`.
