Monitoring reports that node `{{node.worker2}}` is `NotReady`. Workloads
are no longer scheduled there.

Find the cause **on the node** and fix it permanently, so that the node
becomes `Ready` again and stays Ready after a kubelet restart.

Node access: `cka ssh {{node.worker2}}` (you are root there).
