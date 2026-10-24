# Identity at Pod level (applies to every container); the read-only root
# filesystem exists only at container level.
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: {{pod}}
  namespace: {{ns}}
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: {{uid}}
    runAsGroup: {{gid}}
  containers:
    - name: app-container
      image: docker.io/library/busybox:1.37
      command: ["sleep", "3600"]
      securityContext:
        readOnlyRootFilesystem: true
EOF
kubectl -n {{ns}} wait --for=condition=Ready pod/{{pod}} --timeout=120s
kubectl -n {{ns}} exec {{pod}} -- id
kubectl -n {{ns}} exec {{pod}} -- touch /newfile || true
