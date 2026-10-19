Expose the `{{app}}` Deployment in namespace `{{ns}}` outside the cluster.

Create a Service named `{{app}}-np` of type **NodePort** that

- forwards Service port 80 to container port 80 of the `{{app}}` Pods;
- uses the fixed node port **{{nodeport}}**.

Afterwards, `http://<any-node-InternalIP>:{{nodeport}}` must serve the app.
