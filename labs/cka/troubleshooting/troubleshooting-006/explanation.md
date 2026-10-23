## Root cause

`frontend-egress` selects the frontend Pods for **Egress** and allows only
TCP/80 to the backend Pods. Every other packet the frontend sends is dropped,
including DNS queries to CoreDNS (UDP/TCP 53 in `kube-system`). The Service
existed and had endpoints, and connecting by ClusterIP worked. Only name
resolution failed, with `bad address 'backend'`.

## The systematic path

1. Reproduce from the **client**, not the server.
2. Split the problem: by name vs by IP → DNS or connectivity.
3. DNS failing for just one workload, while CoreDNS is healthy → something
   between that client and CoreDNS: egress policy, `dnsPolicy`, a custom
   `dnsConfig`.
4. List the policies selecting the client: `kubectl get netpol -n {{ns}}` and
   read their `podSelector`s.

## Fix choices

- Add a separate DNS-allow policy (reference). Policies are additive.
- Add the DNS rule to `frontend-egress` itself, equally valid.
- Deleting the policy, or allowing all egress, also "fixes" it. The guard
  catches that, because the frontend could then reach `decoy` in
  `{{ns}}-partners`.

A `namespaceSelector` and a `podSelector` in the **same** `to:` item mean
"kube-dns Pods in kube-system". Split into two items, they would mean "anything
in kube-system OR any kube-dns-labelled Pod in this namespace".

## In production

Default-deny egress rollouts break DNS more often than anything else. Many
teams ship a cluster-wide "allow DNS" baseline policy for that reason.
