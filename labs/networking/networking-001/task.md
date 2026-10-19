Requests to the `{{app}}` Service in namespace `{{ns}}` time out, although the
backend Pods are running and Ready.

Make `http://{{app}}.{{ns}}.svc.cluster.local` serve the existing backend Pods.

- Do **not** modify the `{{app}}` Deployment.
- A Pod named `client` in `{{ns}}` is available for testing
  (`kubectl -n {{ns}} exec client -- wget -qO- -T 3 http://{{app}}`).
