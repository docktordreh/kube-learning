kubectl get storageclass
cat <<'EOF' | kubectl apply -f -
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: {{sc}}
provisioner: rancher.io/local-path
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{app}}-data
  namespace: {{ns}}
spec:
  storageClassName: {{sc}}
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 1Gi
---
apiVersion: v1
kind: Pod
metadata:
  name: {{app}}
  namespace: {{ns}}
  labels:
    app: {{app}}
spec:
  containers:
    - name: {{app}}
      image: busybox:1.37
      command: ["sleep", "infinity"]
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: {{app}}-data
EOF
kubectl -n {{ns}} wait --for=condition=Ready pod/{{app}} --timeout=120s
kubectl -n {{ns}} get pvc {{app}}-data
kubectl get pv
