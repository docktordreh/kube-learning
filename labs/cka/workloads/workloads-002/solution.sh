kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=5s || true
kubectl -n {{ns}} get pods -l app={{app}}
kubectl -n {{ns}} rollout history deployment/{{app}}
kubectl -n {{ns}} rollout history deployment/{{app}} --revision=2
kubectl -n {{ns}} rollout undo deployment/{{app}}
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} rollout history deployment/{{app}}
