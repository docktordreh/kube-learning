## From Ingress to the Gateway API

An Ingress mixes infrastructure (which controller, which ports) with
application routing in one object. The Gateway API separates them:

- **GatewayClass** (cluster-scoped, from the platform): which controller
  implements Gateways. Here Traefik's `traefik` class, controller
  `traefik.io/gateway-controller`.
- **Gateway** (per team or shared): listeners with protocol, port, optional
  hostname and TLS, and which namespaces may attach routes (`allowedRoutes`,
  default: the Gateway's own namespace).
- **HTTPRoute** (per application): `parentRefs` to Gateways, `hostnames`, and
  rules with matches (path, header, query, method), filters, and weighted
  `backendRefs`.

Weights are relative: 80 and 20 send about 4 of 5 requests to `web-v1`. Unlike
the replica-ratio canary, the split does not depend on Pod counts.

Status is part of the contract. A Gateway reports `Accepted` and
`Programmed`; each parent of an HTTPRoute reports `Accepted` and
`ResolvedRefs`. `kubectl describe` shows the reason when one is `False`, for
example `NoMatchingListenerHostname` or `BackendNotFound`.

## Implementation details that matter here

Traefik maps a Gateway listener to the entrypoint with the same **port**. Its
`web` entrypoint listens on 8000 inside the Pod (the Service publishes it on
80), so a listener on port 80 is rejected: listener `Accepted=False` with
reason `PortUnavailable`, Gateway `Programmed=False`. Other controllers
provision a new load balancer per Gateway instead. Check the controller's docs
for how listeners map to ports.

## How to recognise problems in production

- Gateway `Programmed=False`: listener port or protocol not supported by the
  controller, or the GatewayClass is not accepted.
- HTTPRoute `Accepted=False` with `NotAllowedByListeners`: the route lives in
  another namespace than `allowedRoutes` permits, or its hostnames do not
  intersect the listener hostname.
- `ResolvedRefs=False` with `RefNotPermitted`: a backend in another namespace
  needs a ReferenceGrant.
- Removing the Ingress before the route is accepted causes an outage. Migrate
  with both in place, then delete.

## Alternatives

- Put `hostname` only on the HTTPRoute and leave the listener open; the guard
  still passes because the route's hostnames restrict it.
- `ingress2gateway` converts existing Ingresses into Gateway API resources as a
  starting point.
