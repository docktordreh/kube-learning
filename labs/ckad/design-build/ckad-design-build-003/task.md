The Deployment `{{app}}` in namespace `{{ns}}` runs the image
`cka-lab/{{app}}:1.0`, built from `{{workdir}}/app`. The content for release
2.0 is already in that directory, and the security team wants the image to
stop running as root.

1. Change the Dockerfile in `{{workdir}}/app` so that containers from the image
   run as user ID `1000` by default.
2. Build the image `cka-lab/{{app}}:2.0` from `{{workdir}}/app`.
3. Save it as an archive at `{{workdir}}/{{app}}-2.0.tar`.
4. Roll the Deployment `{{app}}` to `cka-lab/{{app}}:2.0`. The cluster cannot
   pull images from this machine: copy the image into the cluster with
   `cka image load cka-lab/{{app}}:2.0` first.

Use the host's Docker for building. The `client` Pod in `{{ns}}` can test the
result: `kubectl -n {{ns}} exec client -- wget -qO- http://{{app}}`
