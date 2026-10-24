kubectl -n {{ns}} get pods -l app={{app}} -o wide
kubectl -n {{ns}} events --types=Warning
kubectl describe nodes | grep -A6 'Allocated resources' | head -n 20
kubectl -n {{ns}} set resources deployment {{app}} --requests=cpu=250m
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
