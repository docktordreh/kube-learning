The `{{app}}` Service in namespace `{{ns}}` refuses all connections. The
Pods behind it are `Running` and nobody has touched the Service.

Restore the service so that `http://{{app}}` serves the nginx welcome page
from inside the namespace (a `client` Pod is available). Keep an HTTP
readiness probe on the container.
