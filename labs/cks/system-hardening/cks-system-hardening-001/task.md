The Deployment `{{app}}` in namespace `{{ns}}` runs on node `{{node.worker1}}`.
It must never modify anything below `/etc`. An AppArmor profile for that
purpose is prepared on `{{node.worker1}}` in `/etc/apparmor.d/cka-{{profile}}`,
but it is not active.

1. Load the profile on `{{node.worker1}}` in enforce mode
   (`cka ssh {{node.worker1}}`).
2. Make the `{{app}}` container run under that profile.

Afterwards, `touch /etc/test` inside the container must fail, and the
Deployment must keep 1 ready replica.
