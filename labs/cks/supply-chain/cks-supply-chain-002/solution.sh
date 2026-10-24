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
        object.spec.containers.all(c, c.image.matches('^.+@sha256:[a-f0-9]{64}$')) &&
        (!has(object.spec.initContainers) ||
         object.spec.initContainers.all(c, c.image.matches('^.+@sha256:[a-f0-9]{64}$')))
      message: "all images must use a sha256 digest"
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
        security.example.com/digests: enforced
EOF
sleep 5
kubectl -n {{ns}} scale deployment/unpinned --replicas=1
kubectl -n {{ns}} patch deployment {{app}} --type=json -p='[{"op":"replace","path":"/spec/template/spec/containers/0/image","value":"docker.io/library/nginx:1.31-alpine@sha256:060849a174666c53439dc7cecbf8f67e225c7cbfb1a44ca97915d9a172a81e6d"}]'
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
