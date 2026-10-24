The `{{app}}` Service in namespace `{{ns}}` sends all traffic to the Deployment
`{{app}}-blue`: nginx 1.30, 3 replicas, Pods labelled `app={{app}}` and
`color=blue`.

Release nginx 1.31 with a blue/green switch:

1. Create a Deployment `{{app}}-green` with 3 replicas of
   `docker.io/library/nginx:1.31-alpine`, its Pods labelled `app={{app}}` and
   `color=green`.
2. When all green Pods are ready, move the `{{app}}` Service to them, so that
   every request is answered by nginx 1.31.

- Keep `{{app}}-blue` unchanged and running as the rollback target.
- A Pod named `client` in `{{ns}}` is available for testing. The `Server`
  header shows the answering version:
  `kubectl -n {{ns}} exec client -- wget -S -O /dev/null http://{{app}}`
