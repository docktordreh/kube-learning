## Concepts

RBAC is additive. A subject can do only what some binding grants it. There are
no deny rules, so least privilege means granting exactly the verbs, resources and
API groups needed:

- **Role** holds rules for one namespace; **ClusterRole** holds rules for any
  namespace or for cluster-scoped resources.
- **RoleBinding** grants a Role (or a ClusterRole) *within one namespace*.
  **ClusterRoleBinding** grants cluster-wide, which is the usual way
  over-permissioning happens.
- Deployments are in the `apps` group (`deployments.apps`); Pods are in the core
  group (`""`). Logs are the `pods/log` **subresource** and need their own rule
  entry.

The grader asked the API server through SubjectAccessReviews, which is what
`kubectl auth can-i --as=...` does. Any object names you chose are fine.

## Alternatives

- A ClusterRole bound with a **RoleBinding** in `{{ns}}` is equally correct and
  reusable across namespaces.
- One `kubectl apply` of a YAML Role with two rules.
- Binding the built-in `edit` ClusterRole would fail the guards: it grants
  Secrets and Pod deletion.

## In production

Pipelines that "need cluster-admin" are a classic incident source. Use
`kubectl auth can-i --list --as=system:serviceaccount:<ns>:<sa> -n <ns>` to
audit what an identity really has.
