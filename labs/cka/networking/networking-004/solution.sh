kubectl get gatewayclass traefik
kubectl apply -f - <<'EOF'
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: {{gateway}}
  namespace: {{ns}}
spec:
  gatewayClassName: traefik
  listeners:
    - name: http
      protocol: HTTP
      port: 8000
      hostname: {{host}}
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: {{route}}
  namespace: {{ns}}
spec:
  parentRefs:
    - name: {{gateway}}
  hostnames:
    - {{host}}
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api
      backendRefs:
        - name: api
          port: 80
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: web-v1
          port: 80
          weight: 80
        - name: web-v2
          port: 80
          weight: 20
EOF
kubectl -n {{ns}} wait --for=condition=Programmed gateways.gateway.networking.k8s.io/{{gateway}} --timeout=60s
kubectl -n {{ns}} get httproutes.gateway.networking.k8s.io {{route}} -o jsonpath='{.status.parents[*].conditions[?(@.type=="Accepted")].status}'; echo
# Only now remove the Ingress; the HTTPRoute already serves the host.
kubectl -n {{ns}} delete ingress {{ingress}}
sleep 3
kubectl -n {{ns}} exec client -- wget -qO- --header 'Host: {{host}}' http://traefik.traefik.svc.cluster.local/api
