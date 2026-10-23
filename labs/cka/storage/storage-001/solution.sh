kubectl -n {{ns}} describe pvc {{app}}-data | tail -n 5
kubectl get storageclass
# storageClassName is immutable: recreate the claim. Stop the consumer first so the
# pvc-protection finalizer does not keep the old claim Terminating.
kubectl -n {{ns}} scale deployment {{app}} --replicas=0
kubectl -n {{ns}} wait --for=delete pod -l app={{app}} --timeout=60s || true
kubectl -n {{ns}} get pvc {{app}}-data -o yaml > /tmp/{{app}}-data.yaml
kubectl -n {{ns}} delete pvc {{app}}-data --wait=true
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{app}}-data
  namespace: {{ns}}
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 1Gi
EOF
kubectl -n {{ns}} scale deployment {{app}} --replicas=1
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} get pvc {{app}}-data
