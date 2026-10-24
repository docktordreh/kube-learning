kubectl -n {{ns}} get pods -l app={{app}}
kubectl -n {{ns}} events --types=Warning | grep -i 'readiness probe failed' | head -n 3
POD_IP=$(kubectl -n {{ns}} get pods -l app={{app}} -o jsonpath='{.items[0].status.podIP}')
kubectl -n {{ns}} exec client -- wget -qO- -T 3 "http://${POD_IP}{{wrong_path}}" || echo "{{wrong_path}} fails"
kubectl -n {{ns}} exec client -- wget -qO- -T 3 "http://${POD_IP}/" | head -n 2
kubectl -n {{ns}} patch deployment {{app}} --type=json \
  -p '[{"op":"replace","path":"/spec/template/spec/containers/0/readinessProbe/httpGet/path","value":"/"}]'
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} exec client -- wget -qO- -T 3 http://{{app}} | head -n 4
