Namespace `{{ns}}` runs three backends, each behind a Service on port 80:
`api-service`, `video-service` and `fallback-service`. The cluster's ingress
controller is Traefik (IngressClass `traefik`). Inside the cluster it is
reachable at `http://traefik.traefik.svc.cluster.local`.

Create an Ingress `app-ingress` in `{{ns}}` that:

1. routes host `{{host}}`, path `/api` (`pathType: Prefix`) to `api-service:80`,
2. routes host `{{host}}`, path `/video` (`pathType: Prefix`) to
   `video-service:80`,
3. sends every other path of `{{host}}` to `fallback-service:80`.

Requests for other hosts must not reach these Services.

Test from the `client` Pod:
`kubectl -n {{ns}} exec client -- wget -qO- --header 'Host: {{host}}' http://traefik.traefik.svc.cluster.local/api`
