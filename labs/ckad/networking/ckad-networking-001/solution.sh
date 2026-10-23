kubectl apply -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  namespace: {{ns}}
spec:
  ingressClassName: traefik
  rules:
    - host: {{host}}
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api-service
                port:
                  number: 80
          - path: /video
            pathType: Prefix
            backend:
              service:
                name: video-service
                port:
                  number: 80
          # Longest matching path wins, so / only catches the rest.
          - path: /
            pathType: Prefix
            backend:
              service:
                name: fallback-service
                port:
                  number: 80
EOF
kubectl -n {{ns}} describe ingress app-ingress
sleep 3
kubectl -n {{ns}} exec client -- wget -qO- --header 'Host: {{host}}' http://traefik.traefik.svc.cluster.local/api
