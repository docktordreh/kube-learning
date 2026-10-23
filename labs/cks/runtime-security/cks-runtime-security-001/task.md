The security team wants the containers in namespace `{{ns}}` to be immutable
at runtime: no container may change its own filesystem, and none may run
privileged.

1. Make the root filesystem of the Deployment `{{app}}` read-only. The app
   writes its content to `/tmp` at start-up and must keep serving
   `http://{{app}}`.
2. The Deployment `{{debug}}` runs privileged. Remove that and make its root
   filesystem read-only as well. It must keep running.

Test from the `client` Pod:
`kubectl -n {{ns}} exec client -- wget -qO- http://{{app}}`
