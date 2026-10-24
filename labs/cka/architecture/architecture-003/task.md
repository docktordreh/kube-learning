A small cluster component (a status page) is kept as a Kustomize **base** in
`{{workdir}}/component/base`.

Create a **production overlay** in `{{workdir}}/component/overlays/prod` that
reuses the base unchanged and

- deploys into namespace `{{ns}}` (it exists);
- prefixes all names with `prod-`;
- adds the label `env: prod` to all objects (Deployment and Pod template);
- runs {{replicas}} replicas;
- uses image `docker.io/library/nginx:1.31-alpine`.

Install the overlay into the cluster with kubectl. Do not edit the base.
