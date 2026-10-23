## Concepts

- A **PersistentVolume** is a cluster-scoped piece of storage. A
  **PersistentVolumeClaim** is a namespaced request for storage. The
  PV controller binds one claim to one volume, permanently, until the claim is
  deleted.
- Binding requires the same `storageClassName` (an empty class matches only an
  empty class), a superset of the requested access modes, and capacity ≥ the
  request. `volumeName` in the claim pins a specific PV, and `claimRef` in the
  PV reserves a PV for a specific claim.
- If `storageClassName` is omitted in the claim, the **default** class is
  filled in at admission and a dynamic provisioner creates a new volume. Your
  static PV would then never be used.
- `hostPath` stores data on whichever node runs the Pod. It is fine for labs and
  single-node tools, but it is not a real multi-node storage backend. The
  kubelet creates the directory because of `DirectoryOrCreate`.

## Reclaim policy

With `Retain`, deleting the claim leaves the PV `Released` and keeps the data.
An admin must clean it up and remove `claimRef` before the PV can be reused.
`Delete` removes the backing storage (dynamic provisioners only).

## In production

A Pod stuck `Pending` with `persistentvolumeclaim "<x>" not found` or
`unbound immediate PersistentVolumeClaims` means a claim/volume problem. Use
`kubectl get pv,pvc -A` and compare class, mode and size.
