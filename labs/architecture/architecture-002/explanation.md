## Concepts

- Cluster-scoped resources (nodes, PVs, StorageClasses, namespaces, CRDs)
  can only be granted through a **ClusterRole** bound by a
  **ClusterRoleBinding**. A RoleBinding cannot grant them.
- Kubernetes has no user or group objects. Group membership comes from the
  authenticator: the `O=` fields of a client certificate, an OIDC `groups`
  claim, and so on. Binding to groups keeps RBAC stable when people join or leave.
- `kubectl auth can-i ... --as=<user> --as-group=<group>` uses impersonation
  to test exactly what that identity would get. The grader used
  SubjectAccessReviews with the same semantics.

## Pitfall

`--resource=storageclasses` alone resolves to the right group through
discovery. In YAML you must write `apiGroups: ["storage.k8s.io"]`
yourself. Nodes and PVs are in the core group `""`.
