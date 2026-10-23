kubectl apply -f {{workdir}}/backuppolicy-crd.yaml
kubectl wait --for=condition=Established crd/backuppolicies.ops.cka.example --timeout=60s
kubectl api-resources --api-group=ops.cka.example
# The OpenAPI document is republished a few seconds after the CRD is Established.
for _ in 1 2 3 4 5 6 7 8 9 10; do kubectl explain backuppolicy.spec && break; sleep 3; done
cat <<'EOF' | kubectl apply -f -
apiVersion: ops.cka.example/v1
kind: BackupPolicy
metadata:
  name: nightly
  namespace: {{ns}}
spec:
  schedule: "{{schedule}}"
  retentionDays: {{days}}
  target: postgres-main
EOF
kubectl -n {{ns}} get bp
