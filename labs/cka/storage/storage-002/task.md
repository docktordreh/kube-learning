The Pod `{{app}}` in namespace `{{ns}}` is Pending: its storage was never
provisioned. This legacy app must use a manually managed volume, not
dynamic provisioning.

1. Create a PersistentVolume `{{pv}}`:
   - capacity `{{size}}`, access mode `ReadWriteOnce`;
   - `storageClassName: manual`, reclaim policy `Retain`;
   - backed by `hostPath` `/srv/{{pv}}` (type `DirectoryOrCreate`).
2. Create the PersistentVolumeClaim `{{app}}-claim` in `{{ns}}` that the Pod
   expects, requesting `{{size}}`, so that it binds to `{{pv}}`.

The Pod must start without being recreated.
