kubectl apply -f - <<'EOF'
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: {{policy}}
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods"]
  validations:
    - expression: >-
        object.spec.containers.all(c, c.image.startsWith('docker.io/library/')) &&
        (!has(object.spec.initContainers) ||
         object.spec.initContainers.all(c, c.image.startsWith('docker.io/library/')))
      message: "images must come from docker.io/library/"
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: {{policy}}
spec:
  policyName: {{policy}}
  validationActions: [Deny]
  matchResources:
    namespaceSelector:
      matchLabels:
        security.example.com/image-policy: enforced
EOF
# The API server needs a moment to load a new policy.
sleep 5
kubectl -n {{ns}} scale deployment rogue {{app}}-tools --replicas=1
kubectl -n {{ns}} rollout restart deployment/{{app}}
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
sleep 5
kubectl -n {{ns}} get deployment rogue -o jsonpath='{.status.conditions[?(@.type=="ReplicaFailure")].message}'; echo
