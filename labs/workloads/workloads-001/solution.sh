kubectl -n {{ns}} patch deployment {{app}} -p \
  '{"spec":{"strategy":{"type":"RollingUpdate","rollingUpdate":{"maxUnavailable":0,"maxSurge":{{surge}}}}}}'
kubectl -n {{ns}} set image deployment/{{app}} nginx=docker.io/library/nginx:1.31-alpine
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} scale deployment {{app}} --replicas={{replicas}}
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} rollout history deployment/{{app}}
