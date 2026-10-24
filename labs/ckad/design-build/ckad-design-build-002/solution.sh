kubectl -n {{ns}} get pods -o wide
kubectl describe nodes | grep -E '^Name:|^Taints:'
kubectl -n {{ns}} delete deployment {{agent}}
kubectl apply -f - <<'EOF'
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: {{agent}}
  namespace: {{ns}}
  labels:
    app: {{agent}}
spec:
  selector:
    matchLabels:
      app: {{agent}}
  template:
    metadata:
      labels:
        app: {{agent}}
    spec:
      terminationGracePeriodSeconds: 1
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          operator: Exists
          effect: NoSchedule
      containers:
        - name: agent
          image: docker.io/library/busybox:1.37
          command: ["sh", "-c", "while true; do ls /host/log | wc -l; sleep 60; done"]
          volumeMounts:
            - name: host-logs
              mountPath: /host/log
              readOnly: true
      volumes:
        - name: host-logs
          hostPath:
            path: /var/log
            type: Directory
EOF
kubectl -n {{ns}} rollout status daemonset/{{agent}} --timeout=120s
kubectl -n {{ns}} get pods -o wide
