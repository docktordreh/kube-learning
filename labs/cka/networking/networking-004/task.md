Namespace `{{ns}}` publishes `{{host}}` through the Ingress `{{ingress}}`:
`/api` goes to the Service `api`, everything else to `web-v1`. The platform
team is moving to the Gateway API. The cluster offers the GatewayClass
`traefik`, served by Traefik at `http://traefik.traefik.svc.cluster.local`.

Move `{{host}}` to the Gateway API and start a canary of `web-v2`:

1. Create a Gateway `{{gateway}}` in `{{ns}}` with class `traefik` and one
   HTTP listener on port `8000` (Traefik's `web` entrypoint) for hostname
   `{{host}}`.
2. Create an HTTPRoute `{{route}}` attached to it for `{{host}}`:
   - `/api` (path prefix) goes to Service `api` port 80,
   - everything else goes 80 % to `web-v1` and 20 % to `web-v2` (port 80).
3. When the route works, delete the Ingress `{{ingress}}`.

Requests for other hosts must not reach these Services. Test from the
`client` Pod:
`kubectl -n {{ns}} exec client -- wget -qO- --header 'Host: {{host}}' http://traefik.traefik.svc.cluster.local/`
