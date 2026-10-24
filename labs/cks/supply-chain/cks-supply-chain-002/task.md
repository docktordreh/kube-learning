The release namespace `{{ns}}` must run only content-addressed container
images. Tags can move after deployment, so every Pod image must include a
`sha256` digest.

1. Create ValidatingAdmissionPolicy `{{policy}}` for Pod CREATE and UPDATE
   requests. It must reject every container or init container image that does
   not include a digest.
2. Bind it with ValidatingAdmissionPolicyBinding `{{policy}}`, deny violations,
   and scope the binding to namespaces labelled
   `security.example.com/digests=enforced`.
3. Scale Deployment `unpinned` to one replica and confirm its Pod is rejected.
4. Change Deployment `{{app}}` to use the digest for the supplied
   `docker.io/library/nginx:1.31-alpine` image. It must return to two ready
   replicas.
