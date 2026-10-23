The cluster has no API audit log yet. Enable one on the control-plane node
(`cka ssh {{node.controlplane}}`).

1. Write the audit policy `/etc/kubernetes/audit/policy.yaml`:
   - requests for **Secrets** (in any namespace) are logged at `Metadata` level,
   - all other requests in namespace `{{ns}}` are logged at `RequestResponse`
     level,
   - nothing else is logged,
   - the `RequestReceived` stage is never logged.
2. Configure kube-apiserver to use the policy and write the log to
   `/var/log/kubernetes/audit/audit.log`, keeping log files for at most
   **7 days** and at most **2** old files.

The API server must be healthy again when you are done. Namespace `{{ns}}`
contains the Secret `{{secret}}` and the ConfigMap `{{config}}` for testing.
