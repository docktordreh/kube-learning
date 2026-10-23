The delivery pipeline needs its own identity in namespace `{{ns}}`.

1. Create a ServiceAccount `{{sa}}` in `{{ns}}`.
2. Grant it, **in `{{ns}}` only**, permission to:
   - create, update, patch and delete (and get/list/watch) Deployments;
   - get, list and watch Pods, and read Pod logs.
3. Grant nothing else: no Secrets, no Pod deletion, no other namespace and no
   cluster-scoped resources.

Choose the names of any further objects yourself.
