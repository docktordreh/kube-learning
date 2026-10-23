Several releases of the Helm chart `web` run in this cluster. Two packages of
the chart are in `{{workdir}}/charts`: `web-1.0.0.tgz` (nginx 1.30) and
`web-1.1.0.tgz` (nginx 1.31).

In namespace `{{ns}}`:

1. Uninstall the release `{{app}}-v1`.
2. Upgrade the release `{{app}}-v2` to chart version **1.1.0**.
3. Install a new release `{{app}}-edge` from chart version **1.1.0** with
   **2 replicas**. Set the replica count through Helm values; do not edit
   the chart or the created objects.

Then find the release `vulnerabilities`, which runs somewhere else in the
cluster, and uninstall it.

`helm` is on the PATH of `cka shell` (and of `eval "$(cka lab env)"`).
