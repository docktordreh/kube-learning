## Concepts

A NodePort Service is a ClusterIP Service plus a port, by default from
30000–32767, that kube-proxy opens on **every** node. Traffic to
`<nodeIP>:<nodePort>` is forwarded to a ready endpoint on any node. The Pod
does not need to run on the node you connect to, unless
`externalTrafficPolicy: Local` is set.

- `port`: the Service's own port (ClusterIP:port)
- `targetPort`: the container port (number or name)
- `nodePort`: the node-level port. If omitted, one is allocated randomly;
  if specified, it must be free and inside the range.

LoadBalancer Services build on NodePort: the cloud controller points an
external load balancer at the node ports.

## Alternatives

`kubectl create service nodeport {{app}}-np --tcp=80:80 --node-port={{nodeport}}`
creates the Service with the selector `app={{app}}-np`. You then have to fix
the selector to `app={{app}}`, which makes it an instructive trap. Writing the
YAML by hand is equally fine.

## In production

"Port already allocated" errors mean another Service owns the node port. If
traffic only works via some nodes, check `externalTrafficPolicy`, firewalls and
which nodes host endpoints.
