# Green runs next to blue: same app label, colour green, the new image.
kubectl apply -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{app}}-green
  namespace: {{ns}}
  labels:
    app: {{app}}
    color: green
spec:
  replicas: 3
  selector:
    matchLabels:
      app: {{app}}
      color: green
  template:
    metadata:
      labels:
        app: {{app}}
        color: green
    spec:
      containers:
        - name: nginx
          image: docker.io/library/nginx:1.31-alpine
          ports:
            - name: http
              containerPort: 80
          readinessProbe:
            httpGet:
              path: /
              port: http
            periodSeconds: 2
EOF
# Switch only when green is fully ready.
kubectl -n {{ns}} rollout status deployment/{{app}}-green --timeout=120s
# A merge patch replaces just the colour key of the selector.
kubectl -n {{ns}} patch service {{app}} -p '{"spec":{"selector":{"color":"green"}}}'
kubectl -n {{ns}} get endpointslices -l kubernetes.io/service-name={{app}}
kubectl -n {{ns}} exec client -- wget -S -O /dev/null http://{{app}} 2>&1 | grep Server
