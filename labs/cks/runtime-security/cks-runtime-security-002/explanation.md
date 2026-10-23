## How API auditing works

Every request to kube-apiserver passes through the audit stage. The policy
file decides per request how much to record; the backend (here a log file)
writes JSON lines, one per event:

- **Levels:** `None` (skip), `Metadata` (who, what, when, response code),
  `Request` (plus request body), `RequestResponse` (plus response body).
- **Stages:** `RequestReceived`, `ResponseStarted` (watches), `ResponseComplete`,
  `Panic`. `omitStages: [RequestReceived]` halves the volume without losing
  information.
- **Rules are evaluated in order; the first match wins.** A Secret read in
  `{{ns}}` matches both the Secret rule and the namespace rule, so the Secret
  rule must come first. Otherwise secret values would land in the log in plain
  text at `RequestResponse` level, which is the classic audit-policy mistake.
- A final `level: None` makes everything unmatched silent. Without it, the
  default for unmatched requests is `None` as well, but an explicit rule
  documents the intent.

kube-apiserver runs as a static Pod, so flags go into
`/etc/kubernetes/manifests/kube-apiserver.yaml`. The policy and the log
directory must be mounted into the container (hostPath volumes); a flag that
points at a path without a mount fails at start-up. `--audit-log-maxage`,
`--audit-log-maxbackup` and `--audit-log-maxsize` rotate the file.

## How to recognise problems in production

- API server gone after editing the manifest: the static Pod failed. Use
  `crictl ps -a` and `crictl logs` on the node. Typical causes: YAML
  indentation, a missing volume for the policy path, a policy parse error.
- The audit log grows by gigabytes per day: `RequestResponse` on broad scopes
  (all resources, watches), or no `omitStages`.
- Secrets readable in the audit log: a rule at `Request` or `RequestResponse`
  matched Secrets before the `Metadata` rule.

## Alternatives

- A webhook backend (`--audit-webhook-config-file`) ships events to an
  external collector instead of a file.
- Rules can also select by `users`, `userGroups`, `verbs`, `nonResourceURLs`
  and `resourceNames`, for example to drop the kubelet's or controllers'
  routine reads.
