The security team requires the **restricted** Pod Security Standard for
namespace `{{ns}}`.

1. Make the namespace **enforce** the `restricted` profile.
2. The Deployment `{{app}}` in `{{ns}}` violates it. Change it so that its Pods
   are admitted under enforcement and it runs 2 ready replicas again. The app
   listens on port 8080 and only writes to `/tmp`.

The Service `{{app}}` must keep answering. Test from the `client` Pod:
`kubectl -n {{ns}} exec client -- wget -qO- http://{{app}}`
