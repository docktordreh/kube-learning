Users intermittently get errors from the `{{app}}` Pod in namespace `{{ns}}`.
One of its containers logs lines containing `ERROR`.

1. Write the **name of that container** (only the name) to
   `{{workdir}}/container.txt`.
2. Write **all log lines of that container that contain `ERROR`** to
   `{{workdir}}/errors.log`, unchanged and in their original order.

Both files are on this machine (the host running cka), not on a cluster node.
