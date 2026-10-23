## How blue/green works in Kubernetes

Kubernetes has no blue/green object. The pattern is two complete Deployments
(blue = current, green = new) and one Service whose label selector picks a
colour. Changing the selector makes the EndpointSlice controller replace all
endpoints at once, and kube-proxy follows within seconds. New connections go to
green; established keep-alive connections to blue Pods finish on blue.

Because blue keeps running untouched, rollback is the same one-line selector
change in the other direction. The price is double capacity during the release.

## How to recognise problems in production

- Switching before green is ready: the Service briefly has no or few ready
  endpoints and clients see connection errors. Always wait for
  `kubectl rollout status` first.
- A selector that matches both colours (for example only `app={{app}}`) mixes
  versions: the Service shows 6 endpoints and responses alternate between
  versions. The `endpoints` guard catches that.
- Editing the blue Deployment "to make it green" is a rolling update, not
  blue/green: there is no instant rollback target left.

## Alternatives

- `kubectl -n {{ns}} edit svc {{app}}` and change `color` by hand.
- `kubectl set selector svc {{app}} 'app={{app}},color=green'` replaces the
  whole selector in one command.
- An Ingress or Gateway API HTTPRoute can switch, or split by weight, between
  two Services instead of relabelling one.
