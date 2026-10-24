cd "{{workdir}}"
# Shows which kinds the server no longer serves in these versions.
kubectl apply --dry-run=client -f {{app}}.yaml || true
# One run converts every object to its group's preferred version (output: a List).
kubectl convert -f {{app}}.yaml > {{app}}.converted.yaml
sed -i 's/namespace: {{old_ns}}$/namespace: {{ns}}/' {{app}}.converted.yaml
mv {{app}}.converted.yaml {{app}}.yaml
kubectl apply -f {{app}}.yaml
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} get deploy,svc,pdb,cronjob,ingress
