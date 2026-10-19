## What happened

Revision 3 referenced `nginx:1.31-alpine-hardened`, which does not exist. New
Pods went to `ErrImagePull` / `ImagePullBackOff`. With the default
`maxUnavailable: 25%` the controller only removed one old Pod, so the service
degraded but kept serving. After `progressDeadlineSeconds` the Deployment
reports `Progressing=False, reason ProgressDeadlineExceeded`. Kubernetes never
rolls back on its own.

## Rollback mechanics

`kubectl rollout undo` copies the Pod template of the previous revision (2)
into the Deployment. That is a new template change, so it becomes **revision
4**, and revision 2 disappears from the history list because templates are
de-duplicated. The old ReplicaSet of revision 2 is scaled back up. No Pod
template is rebuilt from scratch.

## Alternatives

`kubectl rollout undo --to-revision=2`, or `kubectl set image ... nginx:1.31-alpine`.
Both produce the same state and are accepted.

## In production

Watch `kubectl rollout status` in CI so that pipelines fail on stuck rollouts.
`kubectl describe deployment` shows the Progressing condition, and the newest
ReplicaSet's Pods show the image error.
