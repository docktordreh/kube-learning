The log agent `{{agent}}` in namespace `{{ns}}` runs as a Deployment with 3
replicas. It is meant to read each node's logs, but some nodes have no agent
and others have two.

Replace it with a DaemonSet `{{agent}}` in `{{ns}}`:

- exactly one agent Pod on **every** node, the control-plane node included,
- Pods labelled `app={{agent}}`, same container as before,
- the node's `/var/log` mounted at `/host/log`, **read-only**.

Delete the Deployment.
