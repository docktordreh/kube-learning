Only images from `docker.io/library/` are approved for namespaces labelled
`security.example.com/image-policy=enforced`, such as `{{ns}}`.

1. Create a ValidatingAdmissionPolicy `{{policy}}` that rejects creating or
   updating a Pod if any of its containers **or init containers** uses an
   image that does not start with `docker.io/library/`.
2. Bind it with a ValidatingAdmissionPolicyBinding, also named `{{policy}}`,
   that **denies** such requests, and only in namespaces carrying that label.
3. Prove it works in `{{ns}}`:
   - scale the Deployments `rogue` and `{{app}}-tools` to 1 replica each; their
     Pods must be rejected,
   - `kubectl rollout restart` the Deployment `{{app}}`; it must come back with
     2 ready replicas.
