The security team has a new least-privilege policy: applications never run as
root, avoid system user IDs, and cannot write to their own filesystem.

In namespace `{{ns}}`, create a Pod `{{pod}}` that follows it:

- The **Pod-level** security context runs every container as UID `{{uid}}` and
  GID `{{gid}}` and enforces `runAsNonRoot`.
- A single container `app-container` runs `docker.io/library/busybox:1.37` and
  keeps running (`sleep 3600`).
- The container's root filesystem is **read-only**: `touch /newfile` fails with
  `Read-only file system`.
