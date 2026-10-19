## Concepts

Container runtimes capture each container's **stdout and stderr** into files on
the node (`/var/log/pods/<ns>_<pod>_<uid>/<container>/N.log`). The kubelet
serves them to `kubectl logs`. Useful flags:

- `-c <container>`: required when a Pod has several containers, unless a
  default container is annotated;
- `--all-containers --prefix`: interleave every container, each line prefixed;
- `--previous`: the last terminated instance (crash loops);
- `--since=10m`, `--tail=50`, `-f`, `--timestamps`;
- `kubectl logs deploy/<name>` / `-l app=x`: pick Pods by owner or selector.

Note the distractor: `errors_total=0` in WARN lines contains "error" in lower
case. `grep ERROR` is case-sensitive on purpose. Read requirements literally.

## In production

Logs exist only as long as the container's log files do: they are rotated by
size and removed with the Pod. Ship them centrally (Fluent Bit, Vector, the
OpenTelemetry collector). If the API server is unavailable, read them with
`crictl logs` on the node.
