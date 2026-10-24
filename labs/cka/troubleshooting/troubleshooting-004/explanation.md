## What was wrong

The readiness probe requested `{{wrong_path}}`, which stock nginx answers
with 404. Any status outside 200–399 counts as failure, so the kubelet kept
the containers `Ready=False`. Unready Pods are published as not-ready in the
Service's EndpointSlices. kube-proxy only forwards to ready endpoints, so the
Service had no backends. With iptables/nftables proxies, the connection was
**refused**.

## Readiness vs liveness vs startup

- **readiness** failing → removed from Service endpoints, never restarted;
- **liveness** failing → container is killed and restarted;
- **startup** → holds off the other probes until the app has started.

A broken readiness probe gives "Running but 0/1 Ready"; a broken liveness probe
gives restart loops.

## Alternatives

Any HTTP path that returns 2xx/3xx is accepted, for example `/` or
`/index.html`. Deleting the probe would also make the Pods Ready, but it hides
real outages and the task forbids it.
