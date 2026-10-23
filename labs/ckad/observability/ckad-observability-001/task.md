The manifest `{{workdir}}/{{app}}.yaml` was written years ago for namespace
`{{old_ns}}`. It no longer applies: several of its API versions were removed
from Kubernetes.

1. Update the manifest so that every object uses an API version this cluster
   serves. Keep what the objects do: 3 replicas, the Service, a disruption
   budget of 2 available Pods, the hourly report CronJob, and the Ingress for
   `{{app}}.example.test`.
2. Make every object target namespace `{{ns}}` instead of `{{old_ns}}`.
3. Save the result **over the original file** and apply it.

The `kubectl convert` plugin is available in `cka shell`.
