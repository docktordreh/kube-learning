kubectl -n {{ns}} describe pod {{app}} | tail -n 4
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolume
metadata:
  name: {{pv}}
spec:
  capacity:
    storage: {{size}}
  accessModes: [ReadWriteOnce]
  storageClassName: manual
  persistentVolumeReclaimPolicy: Retain
  hostPath:
    path: /srv/{{pv}}
    type: DirectoryOrCreate
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{app}}-claim
  namespace: {{ns}}
spec:
  storageClassName: manual
  volumeName: {{pv}}
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: {{size}}
EOF
kubectl -n {{ns}} wait --for=jsonpath='{.status.phase}'=Bound pvc/{{app}}-claim --timeout=60s
kubectl -n {{ns}} wait --for=condition=Ready pod/{{app}} --timeout=90s
kubectl get pv {{pv}}
