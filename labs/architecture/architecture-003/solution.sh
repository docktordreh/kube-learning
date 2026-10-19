kubectl kustomize {{workdir}}/component/base
mkdir -p {{workdir}}/component/overlays/prod
cat > {{workdir}}/component/overlays/prod/kustomization.yaml <<'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
namespace: {{ns}}
namePrefix: prod-
labels:
  - pairs:
      env: prod
    includeTemplates: true
replicas:
  - name: status-page
    count: {{replicas}}
images:
  - name: docker.io/library/nginx
    newTag: 1.31-alpine
EOF
kubectl kustomize {{workdir}}/component/overlays/prod
kubectl apply -k {{workdir}}/component/overlays/prod
kubectl -n {{ns}} rollout status deployment/prod-status-page --timeout=120s
