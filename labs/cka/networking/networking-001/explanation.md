## What was wrong

The Service selector required `tier: {{wrong_tier}}`, but the backend Pods are
labelled `tier: backend`. A Service selects Pods carrying **all** selector pairs,
so the EndpointSlice controller found no Pods and published no endpoints.
kube-proxy therefore had nothing to forward to. Depending on the proxy mode,
connections time out or are rejected.

## How to recognise it in production

- `kubectl get endpointslices -l kubernetes.io/service-name=<svc>` shows no
  addresses (or `kubectl get endpoints <svc>` shows `<none>`), while the Pods are
  Running and Ready.
- DNS still resolves, because the Service and its ClusterIP exist. Only the
  traffic fails. That rules out CoreDNS quickly.
- This usually follows a relabelling, a Helm values change, or a Service copied
  from another app.

## Alternatives

- `kubectl edit service {{app}}` and fix the selector by hand.
- `kubectl set selector service {{app}} 'app.kubernetes.io/name={{app}},tier=backend'`
  (note that `set selector` replaces the whole selector).
- Changing the Pod template labels instead would also route traffic, but it
  modifies the Deployment. The task forbids that, and the guard check detects it.
