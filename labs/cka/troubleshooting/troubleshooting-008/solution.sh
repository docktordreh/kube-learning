kubectl get nodes --request-timeout=3s || echo "API unavailable"
cka node exec {{node.controlplane}} <<'EOF'
crictl ps -a --name kube-apiserver | head -n 3
id=$(crictl ps -a --name kube-apiserver -q | head -n 1)
crictl logs "$id" 2>&1 | tail -n 3
grep -- '--listen-client-urls' /etc/kubernetes/manifests/etcd.yaml
grep -- '--etcd-servers' /etc/kubernetes/manifests/kube-apiserver.yaml
# etcd serves clients on 2379 over TLS; 2380 is the peer port.
sed -i 's#--etcd-servers=.*#--etcd-servers=https://127.0.0.1:2379#' /etc/kubernetes/manifests/kube-apiserver.yaml
EOF
for _ in $(seq 1 60); do kubectl get --raw /readyz --request-timeout=3s >/dev/null 2>&1 && break; sleep 3; done
kubectl wait --for=condition=Ready node --all --timeout=180s
kubectl get nodes
