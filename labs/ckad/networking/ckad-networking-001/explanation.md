## How Ingress routing works

An Ingress is only configuration. An ingress controller (here Traefik, a
cluster component cka installs on demand) watches Ingresses of its
IngressClass and turns each rule into routes. For every request the
controller compares the `Host` header and the path with the rules:

- `pathType: Prefix` matches whole path segments: `/api` matches `/api` and
  `/api/v1`, but not `/apis`. `Exact` matches only the path itself.
- When several paths match, the longest one wins. A `/` Prefix path is
  therefore a catch-all for the host that never steals `/api` or `/video`.
- A request whose host matches no rule gets the controller's own 404
  (Traefik: `404 page not found`).

The Ingress spec also has `spec.defaultBackend` for requests that match no
rule. Controllers implement it differently: Traefik only honours it on an
Ingress **without rules**, and only one per cluster; ingress-nginx uses it
per Ingress. A host catch-all rule behaves the same everywhere.

The controller sends traffic to the Service's endpoints, so the usual Service
rules apply: no ready endpoints means 503 or 404, depending on the controller.

`ingressClassName` selects the controller. Traefik is the default IngressClass
here, so omitting the field also works. In clusters with several controllers
it decides who serves the Ingress.

## How to recognise problems in production

- Every request returns the controller's 404: the `Host` header does not match
  (clients calling by IP or by another name), or the Ingress has no or the wrong
  IngressClass.
- `/api/v1` works but `/api` does not, or the reverse: compare `pathType` and
  trailing slashes.
- A rule points to a Service name or port that does not exist:
  `kubectl describe ingress` shows `<error: endpoints ... not found>`.

## Alternatives

- `kubectl create ingress app-ingress --rule='{{host}}/api*=api-service:80'
  --rule='{{host}}/video*=video-service:80' --rule='{{host}}/*=fallback-service:80'`
  writes the same object imperatively.
- Three separate Ingresses for the same host also work. The controller merges
  rules across Ingresses of its class.
- The Gateway API (Gateway plus HTTPRoute) is the successor of Ingress and
  expresses the same routes with separate roles for platform and app teams.
