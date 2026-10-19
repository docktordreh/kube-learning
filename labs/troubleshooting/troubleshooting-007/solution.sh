kubectl get nodes
kubectl describe node {{node.worker2}} | grep -A8 Conditions
# On the node (interactively: cka ssh {{node.worker2}}):
cka node exec {{node.worker2}} <<'EOF'
systemctl status kubelet --no-pager | head -n 5
journalctl -u kubelet --no-pager | grep -i 'client ca' | tail -n 2
grep clientCAFile /var/lib/kubelet/config.yaml
ls /etc/kubernetes/pki/
sed -i 's#^\(\s*clientCAFile:\).*#\1 /etc/kubernetes/pki/ca.crt#' /var/lib/kubelet/config.yaml
systemctl restart kubelet
sleep 5
systemctl is-active kubelet
EOF
kubectl wait --for=condition=Ready node/{{node.worker2}} --timeout=120s
