kubectl -n {{ns}} get pods -l app={{app}}
kubectl -n {{ns}} describe pods -l app={{app}} --show-events | grep -E 'Image:|Failed|Back-off' | head
kubectl -n {{ns}} set image deployment/{{app}} web=docker.io/library/nginx:1.31-alpine
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
