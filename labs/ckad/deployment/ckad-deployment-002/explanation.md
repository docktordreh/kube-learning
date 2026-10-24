## How a canary works with plain Kubernetes objects

A Service load-balances over every ready Pod its selector matches, regardless
of which Deployment created it. A canary is therefore just a second, small
Deployment whose Pods carry the Service's labels. The traffic share follows the
Pod ratio: 1 canary out of 5 ready Pods gets about 20 % of new connections.
kube-proxy picks endpoints per connection (randomly in iptables mode), so the
split is statistical, not exact.

Each Deployment needs its own selector. If the canary Deployment selected only
`app={{app}}`, both Deployments would claim each other's Pods. Kubernetes warns
against overlapping selectors because the controllers then fight over replicas.

Promoting the canary means rolling the new image out to the stable Deployment
(or scaling the canary up and the stable one down). Rolling back means deleting
the canary.

## How to recognise problems in production

- The canary gets far more or less traffic than planned: count the endpoints
  per version, not the Deployments. Readiness decides who counts.
- Changing the Service selector to include `track` sends all traffic to one
  version, so the canary sees none.
- Errors that only some users see after a release often point to a forgotten
  canary.

## Alternatives

- `kubectl create deployment {{app}}-canary --image=... --replicas=1` followed by
  relabelling the Pod template also works, as long as the selectors stay
  disjoint.
- Exact percentages independent of replica counts need weighted routing: a
  Gateway API HTTPRoute with `backendRefs` weights, an ingress controller, or a
  service mesh.
