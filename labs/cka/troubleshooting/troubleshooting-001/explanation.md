## What was wrong

The ConfigMap volume exposes each key as a file in `mountPath`. So
`/etc/{{app}}/settings.env` existed, but the program sourced
`/etc/{{app}}/settings.conf`. Under `set -e` the shell exited non-zero, and the
kubelet restarted the container with exponential back-off: `CrashLoopBackOff`.

## How to recognise it

- `kubectl get pods`: `RESTARTS` climbing, status `CrashLoopBackOff` or `Error`.
- `kubectl logs <pod> --previous` shows the output of the **crashed** instance;
  the current one may not have logged anything yet.
- `kubectl describe pod` → `Last State: Terminated, Reason: Error, Exit Code: 2`.

## Equally valid fixes

- Change the command to read `settings.env`.
- Project the key under the expected name with `items: [{key: settings.env, path: settings.conf}]`
  (reference solution).
- Add a second key `settings.conf` with the same content. That changes the
  ConfigMap but keeps `settings.env` intact, so it is also accepted.

The grader checks behaviour (the Pod is Ready and wrote the loaded `MODE`), not
which edit you made.
