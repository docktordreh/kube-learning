## AppArmor in Kubernetes

AppArmor is a Linux Security Module: the kernel checks every file, network
and capability access of a confined process against its profile. Profiles
live on the **node**: the kubelet and container runtime only ask the kernel
to start the container under a named profile. That has three consequences:

1. The profile must be **loaded** on every node that may run the Pod
   (`apparmor_parser --replace <file>`; the files in `/etc/apparmor.d` are
   loaded at boot, freshly written ones are not).
2. The Pod refers to the profile's **name** as declared inside the file
   (`profile {{profile}} ...`), not to the file name.
3. Pods must be scheduled only where the profile exists (here a
   nodeSelector). Otherwise they fail with `CreateContainerError`.

Since Kubernetes v1.30 the profile is a field:
`securityContext.appArmorProfile` with `type: RuntimeDefault`, `Localhost`
(plus `localhostProfile`) or `Unconfined`. The older
`container.apparmor.security.beta.kubernetes.io/<container>` annotation still
works but is deprecated. Without a setting, containerd applies its default
profile `cri-containerd.apparmor.d`.

`/proc/<pid>/attr/apparmor/current` shows the active profile and mode
(`enforce` or `complain`). In this profile, `deny /etc/** w` wins over the
broad `file,` rule, so reads below /etc work and writes fail with
`Permission denied`, even for root.

## How to recognise problems in production

- `CreateContainerError` / "apparmor profile not found": the profile is not
  loaded on that node, for example after a reboot without the file in
  `/etc/apparmor.d`, or on a new node. Distribute profiles with a DaemonSet or
  node configuration management.
- Unexpected `Permission denied` for root inside a container: check the
  kernel log on the node (`journalctl -k | grep apparmor="DENIED"`).
- `complain` mode logs violations without blocking, which helps when writing a
  profile.

## Alternatives

- Setting `appArmorProfile` at Pod level applies it to all containers.
- seccomp (`seccompProfile`) filters system calls instead of resources; the
  two complement each other.
