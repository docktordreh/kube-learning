## From Dockerfile to running Pod

1. **Build.** Each Dockerfile instruction adds a layer or sets image
   configuration. `USER 1000` changes no files; it records the default user
   in the image config (`docker image inspect --format '{{.Config.User}}'`).
   Everything after it, including `CMD`, runs as that user.
2. **Tag.** `name:tag` is just a reference to an image digest. `2.0` and
   `1.0` are different images; reusing a tag for new content makes rollouts
   and rollbacks ambiguous.
3. **Ship.** Nodes need the image locally. Normally they pull it from a
   registry. Without one, an archive (`docker save` / `podman save`, docker
   or OCI format) can be authored into each node's containerd. `cka image
   load` does that for kind (`kind load`). On a real node you would use
   `ctr -n k8s.io images author`.
4. **Run.** `imagePullPolicy: Never` tells the kubelet to use only what is on
   the node. `IfNotPresent` would also work; `Always` would try a registry and
   fail.

The image's `USER` is a default. A Pod's `securityContext.runAsUser`
overrides it, and `runAsNonRoot: true` makes the kubelet refuse images that
would run as root. Setting the user in the image means every consumer gets a
non-root container without extra Pod configuration.

## How to recognise problems in production

- `ErrImageNeverPull`: `imagePullPolicy: Never` and the image is missing on
  that node. Load it into every node, not just one.
- `ErrImagePull` / `ImagePullBackOff` for a locally built image: the node
  tried a registry, because the tag looked remote or the policy is `Always`
  (the default for `:latest`).
- After switching to a non-root user: "permission denied" on ports below 1024
  or on files owned by root. Listen on a high port and `chown` writable paths
  in the Dockerfile.

## Alternatives

- `podman build` and `podman save` work the same way. Load the archive with
  `cka image load --archive <file>`.
- `docker save` writes a docker-compatible archive. Recent Docker versions
  also include an OCI `index.json`; both load fine.
- `kubectl edit` or a patched manifest instead of `kubectl set image` roll out
  the same change.
