kubectl -n {{ns}} get deploy,rs,pods
kubectl -n {{ns}} events --types=Warning
kubectl -n {{ns}} describe resourcequota compute
kubectl -n {{ns}} describe limitrange container-limits
# 3 × 100m = 300m ≤ 600m requests.cpu; 3 × 200m = 600m ≤ 1 limits.cpu;
# 3 × 64Mi ≤ 384Mi; 3 × 128Mi ≤ 768Mi; each Pod ≤ 300m / 256Mi (LimitRange type Pod).
kubectl -n {{ns}} set resources deployment {{app}} \
  --requests=cpu=100m,memory=64Mi --limits=cpu=200m,memory=128Mi
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} describe resourcequota compute
