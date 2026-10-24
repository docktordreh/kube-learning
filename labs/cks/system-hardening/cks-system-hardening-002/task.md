The workload `{{app}}` in namespace `{{ns}}` runs with the container runtime's
default privileges. Harden it without changing its image or command:

1. select the `RuntimeDefault` seccomp profile at Pod level;
2. prevent privilege escalation;
3. drop every Linux capability from the container.

Keep one replica ready. Verify the live process with:
`kubectl -n {{ns}} exec deploy/{{app}} -- grep -E '^(CapEff|NoNewPrivs|Seccomp):' /proc/1/status`
