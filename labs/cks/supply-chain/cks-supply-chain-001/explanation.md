## Admission control without a webhook

ValidatingAdmissionPolicy (GA since v1.30) runs CEL expressions inside the API
server, so no webhook server, certificates or extra Pods are needed:

- the **policy** defines which requests it can see (`matchConstraints`) and
  the rules (`validations`, each a CEL expression that must be true);
- the **binding** activates it for a scope (`matchResources`, here a
  namespace selector) with actions: `Deny`, `Warn` and/or `Audit`.

A policy without a binding has no effect. A binding without a namespace
selector applies cluster-wide, including `kube-system`, whose images come from
`registry.k8s.io`. Scoping keeps a supply-chain rule from breaking the control
plane.

Image references are checked as written in the Pod spec. `nginx:1.31` and
`docker.io/library/nginx:1.31` pull the same image, but only the fully
qualified one passes a prefix check, which is why policies usually require
full names. Prefix checks also need the trailing slash:
`docker.io/library` would match `docker.io/library-evil/...`.

Deployments do not create Pods themselves. The ReplicaSet controller does, and
gets the denial. It surfaces as `FailedCreate` events on the ReplicaSet and as
a `ReplicaFailure` condition on the Deployment. That is where to look when
"nothing happens" after a scale-up.

## How to recognise problems in production

- New Pods never appear, but the Deployment shows no error in `kubectl get`:
  check `kubectl describe rs` for `FailedCreate ... denied request`.
- A CEL error such as `no such key: initContainers` means the expression
  touched an absent optional field. Guard it with `has()`.
- `failurePolicy: Fail` also rejects requests when the expression itself errors.
  `Ignore` fails open.

## Alternatives

- `matchConditions` can exempt requests (for example by service account)
  before validations run.
- Kyverno or Gatekeeper add mutation, reporting and image signature checks.
  Signature verification (cosign) goes beyond a registry allowlist.
- The older ImagePolicyWebhook admission plugin delegates the decision to an
  external service.
