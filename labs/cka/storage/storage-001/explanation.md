## What was wrong

The claim asked for StorageClass `{{wrong_class}}`, which does not exist. No
provisioner watches that class, so the claim stays `Pending` forever, and the
Pod that needs it cannot be scheduled. The scheduler reports unbound immediate
PersistentVolumeClaims, or waits on the claim.

When a PVC **omits** `storageClassName`, the DefaultStorageClass admission
plugin fills in the class annotated
`storageclass.kubernetes.io/is-default-class: "true"` (on kind that is
`standard`, backed by local-path-provisioner with `WaitForFirstConsumer`).
Setting `storageClassName: ""` explicitly means "no class: bind only to a
pre-created PV". That is a common trap.

## Why the claim had to be recreated

Most of a PVC's `spec` is immutable after creation (only the requested size of
expandable classes may grow). The `kubernetes.io/pvc-protection` finalizer
blocks deletion while a Pod uses the claim, so stop the consumer first.

## In production

`kubectl describe pvc` events such as *storageclass.storage.k8s.io
"<name>" not found* or *waiting for a volume to be created by external
provisioner* point straight at class or CSI driver problems. Manifests copied
between clusters or cloud providers with different class names cause this
regularly.
