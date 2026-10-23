Configure the `{{app}}` Deployment in namespace `{{ns}}`:

1. Create a ConfigMap `{{app}}-settings` with the key `LOG_LEVEL` set to `{{level}}`.
2. Create a Secret `{{app}}-db` with the key `password` set to `{{password}}`.
3. Change the Deployment so that
   - the container receives the environment variable `LOG_LEVEL` from the ConfigMap;
   - the Secret is mounted **read-only** at `/etc/{{app}}/db`, so the
     password is readable from `/etc/{{app}}/db/password`.

The Deployment must be available afterwards.
