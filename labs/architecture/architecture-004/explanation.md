## Concepts

A **CustomResourceDefinition** teaches the API server a new resource type.
After `Established=True`, the type is served like a built-in one: RBAC,
`kubectl get/explain`, watches, and validation through the OpenAPI v3 schema.
It does nothing by itself. An **operator** is a controller that watches
those objects and acts on them. Installing an operator usually means
CRDs + RBAC + a controller Deployment (often via Helm or an OLM bundle).

Useful discovery commands:

- `kubectl get crd`, `kubectl api-resources --api-group=<group>`
- `kubectl explain <kind>.spec --recursive`

## Pitfalls

- Quoting: `retentionDays: "7"` is rejected by the schema (string vs
  integer). A cron schedule must be quoted because `*` has meaning in YAML.
- `kubectl explain` may report `couldn't find resource` for a few seconds
  after the CRD becomes Established, while the aggregated OpenAPI document is
  republished. Wait and retry.
- Deleting a CRD deletes **all** its custom resources cluster-wide. Treat CRD
  removal as a data-destroying operation.
