# Diagnose: the Service has no endpoints.
kubectl -n {{ns}} get endpointslices -l kubernetes.io/service-name={{app}}
# Compare the Service selector with the Pod labels.
kubectl -n {{ns}} get service {{app}} -o jsonpath='{.spec.selector}'; echo
kubectl -n {{ns}} get pods --show-labels
# Fix the Service selector (tier=backend is what the Pods carry).
kubectl -n {{ns}} patch service {{app}} --type=merge -p '{"spec":{"selector":{"tier":"backend"}}}'
# Verify.
kubectl -n {{ns}} get endpointslices -l kubernetes.io/service-name={{app}}
kubectl -n {{ns}} exec client -- wget -qO- -T 3 http://{{app}} | head -n 4
