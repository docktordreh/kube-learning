The audit team needs volumes whose data survives when their claims are
deleted.

1. Create a StorageClass `{{sc}}` that
   - uses the provisioner `rancher.io/local-path` (already installed);
   - keeps volumes when claims are deleted (`Retain`);
   - delays binding until a Pod uses the claim;
   - allows volume expansion;
   - is **not** the cluster's default class (`standard` stays the default).
2. In namespace `{{ns}}` create a 1Gi ReadWriteOnce PVC `{{app}}-data` using
   that class, and a Pod `{{app}}` (label `app={{app}}`, image `busybox:1.37`,
   command `sleep infinity`) that mounts it at `/data`.
