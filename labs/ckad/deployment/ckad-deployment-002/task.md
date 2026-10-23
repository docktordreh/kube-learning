The `{{app}}` Deployment in namespace `{{ns}}` runs nginx 1.30 with 5
replicas. The `{{app}}` Service selects its Pods by `app={{app}}`.

Try nginx 1.31 as a canary that answers about 20 % of the requests:

1. Create a Deployment `{{app}}-canary` with 1 replica of
   `docker.io/library/nginx:1.31-alpine` whose Pods the existing Service
   selects.
2. Scale `{{app}}` down to 4 replicas, so the Service keeps 5 Pods in total.

- Do not change the Service.
- A Pod named `client` in `{{ns}}` is available for testing. The `Server`
  header shows the answering version:
  `kubectl -n {{ns}} exec client -- wget -S -O /dev/null http://{{app}}`
