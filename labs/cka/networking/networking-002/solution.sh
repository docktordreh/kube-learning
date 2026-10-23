kubectl -n {{ns}} get networkpolicy
kubectl -n {{ns}} get pods --show-labels
cat <<'EOF' | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend
  namespace: {{ns}}
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              role: frontend
      ports:
        - protocol: TCP
          port: {{port}}
EOF
kubectl -n {{ns}} exec frontend -- wget -qO- -T 3 http://api:{{port}} | head -n 4
kubectl -n {{ns}} exec batch -- wget -qO- -T 3 http://api:{{port}} || echo "batch denied (expected)"
