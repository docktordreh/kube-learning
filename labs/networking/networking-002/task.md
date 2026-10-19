Namespace `{{ns}}` denies all ingress traffic by default. The `api` Service
should now become reachable, but only in a narrow way.

Create a NetworkPolicy named `allow-frontend` in `{{ns}}` so that:

- Pods labelled `role=frontend` **in namespace `{{ns}}`** can connect to the
  `api` Pods on TCP port {{port}};
- nothing else can reach the `api` Pods: no other Pods in `{{ns}}`, no Pods in
  other namespaces (even if labelled `role=frontend`), and no other ports;
- the existing `default-deny-ingress` policy stays in place.

Test Pods: `frontend` and `batch` in `{{ns}}`, `frontend` in `{{ns}}-ops`.
