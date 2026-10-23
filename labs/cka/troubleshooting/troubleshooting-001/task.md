After a configuration refactoring, the `{{app}}` Deployment in namespace
`{{ns}}` never becomes available. Its Pods keep restarting.

Find the cause and fix it so that both replicas run and load their settings
from the existing ConfigMap `{{app}}-config`.

Do not change the settings content of the ConfigMap.
