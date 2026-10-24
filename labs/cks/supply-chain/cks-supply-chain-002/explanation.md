## Tags and digests

An image tag is a mutable name. A registry owner can move `:stable` or even a
version tag to different content. A digest is a cryptographic content address;
`image:tag@sha256:...` records which manifest the workload expects.

The policy checks the Pod admission object, not the registry response. It
therefore enforces the deployment contract but does not prove that an image
was signed, scanned, or built by a trusted pipeline. Registry admission,
signature verification, and provenance attestations complement this rule.

ValidatingAdmissionPolicy runs CEL in the API server. The expression must
check both `containers` and optional `initContainers`; an omitted
`initContainers` field needs a `has()` guard. The binding supplies the scope
and turns a true/false validation into a `Deny` action.

## Production symptoms

- A Deployment stays below its desired replica count: inspect ReplicaSet
  events for an admission denial rather than assuming an image-pull failure.
- A digest-pinned rollout fails to pull: verify the digest exists for the
  cluster architecture and that registry credentials permit the pull.
- A policy rejects system workloads: use a namespace selector and explicit
  exemptions instead of applying a workload policy to `kube-system`.

## Alternatives

Admission policies can require an approved registry prefix, image signatures,
or labels supplied by a trusted build process. Kyverno, Gatekeeper, and
registry policy systems provide richer reporting and verification than this
small digest rule. Keep digest resolution in CI so operators do not guess a
value during deployment.
