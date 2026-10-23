# The canary carries the Service's label (app) plus its own track label, so its
# Deployment selector does not overlap with the stable one (app + track=stable).
kubectl apply -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{app}}-canary
  namespace: {{ns}}
  labels:
    app: {{app}}
    track: canary
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {{app}}
      track: canary
  template:
    metadata:
      labels:
        app: {{app}}
        track: canary
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
kubectl -n {{ns}} rollout status deployment/{{app}}-canary --timeout=120s
kubectl -n {{ns}} scale deployment {{app}} --replicas=4
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} get endpointslices -l kubernetes.io/service-name={{app}}
