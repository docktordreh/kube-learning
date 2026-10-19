## What was wrong

The tag `1.31-alpnie` (transposed letters) does not exist. The kubelet asks the
container runtime to pull the image. The pull fails (`ErrImagePull`), and the
kubelet retries with exponential back-off (`ImagePullBackOff`, up to 5 minutes
between attempts).

## Recognising pull failures

`kubectl describe pod` → Events:

- `manifest unknown` / `not found`: wrong repository or tag;
- `unauthorized` / `pull access denied`: private registry without
  `imagePullSecrets`, or a misspelt repository;
- `dial tcp ... i/o timeout` / `no such host`: the node cannot reach the
  registry (DNS, proxy, air gap).

On a node, `crictl pull <image>` reproduces the pull with the runtime's own
error message.

## Alternatives

`kubectl edit deployment` or `kubectl patch` give the same result. The grader
accepts `nginx:1.31-alpine` with or without the `docker.io/library/` prefix.
