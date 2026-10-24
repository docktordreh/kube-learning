## Seccomp and Linux capabilities

Seccomp filters system calls. `RuntimeDefault` asks the container runtime for
its maintained default profile, which blocks common dangerous calls while
avoiding a profile file on each node. A `Localhost` profile gives tighter
control but requires distributing and loading the same file on every eligible
node.

`allowPrivilegeEscalation: false` sets Linux `no_new_privs` before the process
starts. Setuid binaries and file capabilities cannot grant additional
privileges after that point. Dropping all capabilities removes ambient Linux
privileges such as raw network access and mount administration. These settings
are complementary: seccomp limits system calls, while capabilities limit what
permitted calls can do.

The live process exposes useful evidence in `/proc/1/status`: `Seccomp: 2`
means a filter is active, `NoNewPrivs: 1` means privilege escalation is
disabled, and an all-zero `CapEff` means no effective capabilities remain.

## Production symptoms

- A workload fails after dropping capabilities: identify the required action
  and add only its specific capability, never restore `privileged: true`.
- A Pod is rejected with a seccomp profile error: use `RuntimeDefault` or
  distribute the named Localhost profile to every schedulable node.
- A process still has `NoNewPrivs: 0`: the setting is missing or was placed
  under the wrong container. `allowPrivilegeEscalation` is container-level.

## Alternatives

Pod Security `restricted` requires a seccomp profile, forbids privilege
escalation, and requires dropping capabilities. Admission policy can enforce
additional capability and profile choices. Runtime detection tools can alert
on blocked syscalls, unexpected binaries, and capability use.
