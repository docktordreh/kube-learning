## What was wrong

ResourceQuota `compute` constrains `requests.*` and `limits.*`. With such a
quota, the API server **rejects** any Pod that does not declare those values.
The ReplicaSet controller therefore got `403 Forbidden ... must specify
limits.cpu, limits.memory, requests.cpu, requests.memory` on every create. The
Deployment shows 0 Pods, and the error is only visible in ReplicaSet events
(`ReplicaFailure` condition, `FailedCreate`).

The LimitRange adds a second constraint: no single **Pod** may exceed 300m
CPU / 256Mi memory in total. Values that are too large fail with
`maximum cpu usage per Pod is 300m`. Values that fit per Pod but are too large in
total fail on the quota for the third replica.

Watch out for `type: Container` LimitRanges with only `max`: Kubernetes then
**defaults** missing limits *and* requests to that max. The Pods would be
admitted with surprisingly large reservations, and quota would run out after
one or two replicas.

## Equally valid fixes

- `kubectl set resources` (reference), or editing the Pod template.
- Any values that fit both constraints pass. The grader checks that 3 replicas
  run and that the policies are unchanged.
- A cluster admin could also add `default`/`defaultRequest` to a LimitRange, but
  the task forbids changing the policies.

## In production

When a Deployment is "stuck at 0", run `kubectl describe rs`. Quota
exhaustion shows up as `exceeded quota: compute, requested: ..., used: ...,
limited: ...`. Use `kubectl describe quota` to see usage against limits.
