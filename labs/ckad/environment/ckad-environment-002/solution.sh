cd "{{workdir}}"
cat {{app}}-deployment.yaml
# Same Deployment, plus a container-level securityContext.
cat > {{app}}-deployment-new.yaml <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{app}}-deployment
  namespace: {{ns}}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: {{app}}
  template:
    metadata:
      labels:
        app: {{app}}
    spec:
      terminationGracePeriodSeconds: 1
      containers:
        - name: {{app}}-container
          image: docker.io/library/busybox:1.37
          command: ["sh", "-c"]
          args:
            - |
              echo "user id: $(id -u)"
              grep -E '^(Cap|NoNewPrivs)' /proc/self/status
              while true; do sleep 30; done
          securityContext:
            runAsUser: {{uid}}
            allowPrivilegeEscalation: false
            capabilities:
              add: ["NET_BIND_SERVICE", "NET_RAW", "NET_ADMIN"]
EOF
kubectl apply -f {{app}}-deployment-new.yaml
kubectl -n {{ns}} rollout status deployment/{{app}}-deployment --timeout=120s
kubectl -n {{ns}} logs deployment/{{app}}-deployment
