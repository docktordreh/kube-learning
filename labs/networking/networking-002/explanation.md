## Concepts

- Once **any** policy selects a Pod for a direction (Ingress here), only
  traffic explicitly allowed by some policy is accepted. Policies are additive.
  There are no deny rules, so "default deny + specific allows" is the standard
  pattern.
- Inside `from:`:
  - `podSelector` alone → Pods in **the policy's namespace**;
  - `namespaceSelector` alone → all Pods in matching namespaces;
  - both in **one** list item → Pods matching both (AND);
  - two separate list items → either (OR). A misplaced `-` here is the most
    common NetworkPolicy bug.
- `ports:` restricts the destination port on the selected Pods. The policy
  refers to **container** ports, not Service ports. Here they are equal.
- Policies only work if the CNI plugin enforces them. kindnet does since
  kind v0.24, and so do Calico and Cilium. Flannel alone does not.

## Alternatives

Selecting the api Pods with `matchExpressions`, or naming the port
(`port: http`) instead of the number, is equally valid.

## In production

Symptom: connections time out (packets are dropped, not rejected). Use
`kubectl get networkpolicy -A` and check which policies select the destination
Pod **and** the source Pod. Egress policies on the client side matter too.
