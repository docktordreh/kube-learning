The `{{app}}` Deployment in namespace `{{ns}}` runs `nginx:1.30-alpine`.

1. Configure its rolling update so that no Pod is ever unavailable during an
   update (`maxUnavailable: 0`) and at most {{surge}} extra Pod(s) are created
   (`maxSurge: {{surge}}`).
2. Then update the container image to `nginx:1.31-alpine` with a rolling
   update. Do not recreate the Deployment, because the revision history must be
   kept for a rollback.
3. Scale the Deployment to {{replicas}} replicas.
