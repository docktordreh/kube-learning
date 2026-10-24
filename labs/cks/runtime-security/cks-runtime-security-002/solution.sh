cka node exec {{node.controlplane}} <<'EOF'
set -eu
cat > /etc/kubernetes/audit/policy.yaml <<'POLICY'
apiVersion: audit.k8s.io/v1
kind: Policy
omitStages:
  - RequestReceived
rules:
  # First match wins: Secrets before the namespace rule.
  - level: Metadata
    resources:
      - group: ""
        resources: ["secrets"]
  - level: RequestResponse
    namespaces: ["{{ns}}"]
  - level: None
POLICY
manifest=/etc/kubernetes/manifests/kube-apiserver.yaml
sed -i '/^    - kube-apiserver$/a\
    - --audit-policy-file=/etc/kubernetes/audit/policy.yaml\
    - --audit-log-path=/var/log/kubernetes/audit/audit.log\
    - --audit-log-maxage=7\
    - --audit-log-maxbackup=2' "$manifest"
sed -i '/^    volumeMounts:$/a\
    - mountPath: /etc/kubernetes/audit\
      name: audit-policy\
      readOnly: true\
    - mountPath: /var/log/kubernetes/audit\
      name: audit-log' "$manifest"
sed -i '/^  volumes:$/a\
  - hostPath:\
      path: /etc/kubernetes/audit\
      type: Directory\
    name: audit-policy\
  - hostPath:\
      path: /var/log/kubernetes/audit\
      type: DirectoryOrCreate\
    name: audit-log' "$manifest"
EOF
# The kubelet restarts kube-apiserver; wait until it answers again.
sleep 10
for _ in $(seq 1 60); do kubectl get --raw /readyz --request-timeout=3s >/dev/null 2>&1 && break; sleep 3; done
kubectl -n {{ns}} get secret {{secret}} -o name
