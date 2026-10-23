charts="{{workdir}}/charts"
helm list -A
helm uninstall {{app}}-v1 --namespace {{ns}}
helm upgrade {{app}}-v2 "$charts/web-1.1.0.tgz" --namespace {{ns}}
helm show values "$charts/web-1.1.0.tgz"
helm install {{app}}-edge "$charts/web-1.1.0.tgz" --namespace {{ns}} --set replicaCount=2
# `helm list -A` shows that vulnerabilities lives in {{other_ns}}.
helm uninstall vulnerabilities --namespace {{other_ns}}
kubectl -n {{ns}} rollout status deployment/{{app}}-v2 --timeout=120s
kubectl -n {{ns}} rollout status deployment/{{app}}-edge --timeout=120s
helm history {{app}}-v2 --namespace {{ns}}
