kubectl -n {{ns}} logs deploy/frontend --tail=3
kubectl -n {{ns}} exec deploy/frontend -- wget -qO- -T 3 http://backend || echo "by name: fails"
BACKEND_IP=$(kubectl -n {{ns}} get service backend -o jsonpath='{.spec.clusterIP}')
kubectl -n {{ns}} exec deploy/frontend -- wget -qO- -T 3 "http://${BACKEND_IP}" | head -n 2   # by IP: works
kubectl -n {{ns}} exec deploy/frontend -- cat /etc/resolv.conf
kubectl -n {{ns}} get networkpolicy frontend-egress -o yaml
# DNS is blocked by the egress policy. Allow DNS to CoreDNS only.
cat <<'EOF' | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: frontend-allow-dns
  namespace: {{ns}}
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
EOF
sleep 3
kubectl -n {{ns}} exec deploy/frontend -- wget -qO- -T 3 http://backend | head -n 4
