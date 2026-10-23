The database team is introducing a backup operator. Its API definition is in
`{{workdir}}/backuppolicy-crd.yaml`.

1. Install the CustomResourceDefinition from that file, unchanged.
2. Create a `BackupPolicy` named `nightly` in namespace `{{ns}}` with
   - schedule `{{schedule}}`,
   - retention of {{days}} days,
   - target `postgres-main`.

Use `kubectl explain` to find the exact field names.
