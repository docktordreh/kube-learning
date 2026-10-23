## Concepts

A Deployment manages ReplicaSets. Changing the **Pod template** (here, the
image) creates a new ReplicaSet and a new revision. The controller then scales
the new ReplicaSet up and the old one down within these bounds:

- `maxSurge`: how many Pods above `replicas` may exist during the update;
- `maxUnavailable`: how many below `replicas` may be unavailable.

`maxUnavailable: 0` with `maxSurge ≥ 1` gives zero-downtime updates, provided
readiness probes are honest. A Pod counts as available only when it is Ready.

Scaling changes `replicas` only, not the template, so it does **not** create a
new revision. Old ReplicaSets stay at 0 replicas (`revisionHistoryLimit`, default
10), and `kubectl rollout undo` uses them.

## Alternatives

`kubectl edit deployment` for everything at once, or a single
`kubectl apply` of a modified manifest. Both are equally valid.

## In production

Stalled rollouts with `maxUnavailable: 0` usually mean the new Pods never
become Ready. Check `kubectl rollout status` and the new ReplicaSet's Pods, and
roll back with `kubectl rollout undo`.
