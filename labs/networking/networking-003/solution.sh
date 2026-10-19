kubectl -n {{ns}} expose deployment {{app}} --name={{app}}-np --type=NodePort \
  --port=80 --target-port=80 --dry-run=client -o yaml > /tmp/{{app}}-np.yaml
# Pin the node port, then create the Service.
sed -i 's/^\(\s*\)targetPort: 80$/\1targetPort: 80\n\1nodePort: {{nodeport}}/' /tmp/{{app}}-np.yaml
kubectl apply -f /tmp/{{app}}-np.yaml
kubectl -n {{ns}} get service {{app}}-np
NODE_IP=$(kubectl get node {{node.worker2}} -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')
kubectl -n {{ns}} exec client -- wget -qO- -T 3 "http://${NODE_IP}:{{nodeport}}" | head -n 4
