The security team flagged the Deployment `{{app}}-deployment` in namespace
`{{ns}}`: it runs with the default security settings. Its manifest is at
`{{workdir}}/{{app}}-deployment.yaml`.

Harden the Deployment so that its containers:

1. run as user ID `{{uid}}`,
2. cannot gain more privileges than their parent process
   (`allowPrivilegeEscalation: false`),
3. get the Linux capabilities `NET_BIND_SERVICE`, `NET_RAW` and `NET_ADMIN`.

- Save the modified manifest as `{{workdir}}/{{app}}-deployment-new.yaml` and
  apply it.
- The Deployment must keep 2 ready replicas. The container logs print the user
  ID and capability masks.
