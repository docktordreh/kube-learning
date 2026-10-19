Members of the identity-provider group `{{group}}` need read-only insight into
cluster capacity.

Create a ClusterRole `{{role}}` that allows `get`, `list` and `watch` on
**nodes**, **persistentvolumes** and **storageclasses**, and nothing else.
Bind it cluster-wide to the **group** `{{group}}` with a ClusterRoleBinding,
also named `{{role}}`.

Do not grant anything to individual users.
