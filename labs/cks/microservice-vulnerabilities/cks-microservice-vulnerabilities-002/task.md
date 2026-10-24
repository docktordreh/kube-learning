The application in namespace `{{ns}}` uses Secret `{{secret}}` for a
credential. The credential must not appear in a process environment, because
environment values can leak through diagnostics and crash reports.

Change Deployment `{{app}}` so that:

1. it no longer receives `APP_PASSWORD` from the Secret as an environment
   variable;
2. it reads the Secret as a read-only volume mounted at `/run/secrets/app`;
3. it keeps one ready replica and continues serving the client Pod.

The Secret key is `password`. Verify it with:
`kubectl -n {{ns}} exec deploy/{{app}} -- cat /run/secrets/app/password`
